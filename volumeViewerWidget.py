#!/usr/bin/python3

from PyQt5.QtWidgets import QWidget, QSlider, QLabel, QScrollArea, \
        QHBoxLayout, QVBoxLayout, QSizePolicy, QSpinBox, QPushButton
from PyQt5.QtGui import QImage, QPixmap, QPalette
from PyQt5.QtCore import Qt, pyqtSlot, QPoint
from skimage.restoration import (denoise_tv_chambolle, denoise_bilateral,
                                 denoise_wavelet, estimate_sigma,denoise_nl_means)

import numpy as np
import SimpleITK as sitk
import cv2
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
from preprocess.Smoothing import meanSmooth, guassianSmooth, medianSmooth
from skimage import transform

class scalableLabel(QScrollArea):
    # scaleMin = 0.2
    scaleMin = 0.1
    scaleMax = 10
    wheelScale = 1/200.0
    def __init__(self, parent=None):
        super(scalableLabel, self).__init__(parent)
        self.imageLabel = QLabel(parent)
        self.imageLabel.setBackgroundRole(QPalette.Base)
        self.imageLabel.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.imageLabel.setScaledContents(True)

        self.setBackgroundRole(QPalette.Dark)
        self.setWidget(self.imageLabel)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.__pixmap = None
        self.__scaleFactor = 1 # defalut scaleFactor
        self.__mouseLeftPressing = False
        self.__mouseLeftPos = QPoint(0,0)

    def setScale(self, scale):
        scale = np.clip(scale, self.scaleMin, self.scaleMax)
            
        if self.__pixmap is None:
            return
        self.__scaleFactor = scale
        scaledPixmap = self.__pixmap.scaled(self.__pixmap.size() * scale)
        self.imageLabel.setPixmap(scaledPixmap)
        self.imageLabel.adjustSize()

    def getScale(self):
        return self.__scaleFactor

    def setPixmap(self, pixmap):
        self.__pixmap = pixmap
        scaledPixmap = self.__pixmap.scaled(\
                self.__pixmap.size() * self.__scaleFactor)
        self.imageLabel.setPixmap(scaledPixmap)
        self.imageLabel.adjustSize()

    def wheelEvent(self, event):
        self.setScale(self.getScale() + event.angleDelta().y()*self.wheelScale)

    def mousePressEvent(self, event):
        if (event.button() == Qt.LeftButton):
            self.__mouseLeftPressing = True
            self.__mouseLeftPressPos = event.pos()
        else:
            super(scalableLabel, self).mousePressEvent(event)
            
    def mouseMoveEvent(self, event):
        if self.__mouseLeftPressing and (event.buttons() & Qt.LeftButton):
            currentPos = event.pos()
            hScrollBar = self.horizontalScrollBar()
            vScrollBar = self.verticalScrollBar()
            viewportSize = self.viewport().size()
            delta = currentPos - self.__mouseLeftPressPos
            self.__mouseLeftPressPos = currentPos
            hScrollBar.setValue(hScrollBar.value() - delta.x())
            vScrollBar.setValue(vScrollBar.value() - delta.y())
        else:
            super(scalableLabel, self).mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.LeftButton):
            self.__mouseLeftPressing = False
        else:
            super(scalableLabel, self).mouseReleaseEvent(event)


class volumeSliceViewerWidget(pg.GraphicsLayoutWidget):
    defaultLabelColormap = np.array([ \
            [0  ,0  ,0  ], \
            [0  ,0  ,255], \
            [0  ,255,0  ], \
            [255,0  ,0  ], \
            [0  ,255,255], \
            [255,255,0  ], \
            [255,0  ,255]] + \
            [[0  ,0  ,0 ]]*(256-7), dtype=np.uint8).reshape((256, 1, 3))

    def __init__(self, parent=None, \
            image=None, label=None, \
            index=0, opacity=1, window=[None, None], \
            colormap=None, \
            labelColormap=None):
        '''
        display one slice of a volume
        image: sitk.Image, 3D image only
        window: if None, will be set to [minPixel, maxPixel]
        '''
        # super(volumeSliceViewerWidget, self).__init__(parent=parent)
        pg.GraphicsWindow.__init__(self)
        pg.setConfigOptions(imageAxisOrder='row-major')
        # pg.mkQApp()

        # self.win = pg.GraphicsLayoutWidget()
        self.setWindowTitle('pyqtgraph example: Image Analysis')

        # print('1')
        self.p_a = self.addPlot(row=0, col=0)
        # self.p_a.setAspectLocked()
        self.p_a.hideAxis('bottom')
        self.p_a.hideAxis('left')

        self.p_s = self.addPlot(row=0, col=1)
        self.p_s.hideAxis('bottom')
        self.p_s.hideAxis('left')

        self.p_c = self.addPlot(row=1, col=1)
        self.p_c.hideAxis('bottom')
        self.p_c.hideAxis('left')

        # Item for displaying image data
        # print('2')
        self.img_s = pg.ImageItem()
        self.img_a = pg.ImageItem()
        self.img_c = pg.ImageItem()
        self.p_s.addItem(self.img_s)
        self.p_a.addItem(self.img_a)
        self.p_c.addItem(self.img_c)

        # self.win.resize(800, 800)
        # self.win.show()

        # print('3')
        self.label = pg.LabelItem(justify='right')
        # self.win.addItem(self.label)
        self.addItem(self.label)

        # print('4')
        self.vLine_a = pg.InfiniteLine(angle=90, movable=False)
        self.hLine_a = pg.InfiniteLine(angle=0, movable=False)
        self.p_a.addItem(self.vLine_a, ignoreBounds=True)
        self.p_a.addItem(self.hLine_a, ignoreBounds=True)

        self.vLine_s = pg.InfiniteLine(angle=90, movable=False)
        self.hLine_s = pg.InfiniteLine(angle=0, movable=False)
        self.p_s.addItem(self.vLine_s, ignoreBounds=True)
        self.p_s.addItem(self.hLine_s, ignoreBounds=True)

        self.vLine_c = pg.InfiniteLine(angle=90, movable=False)
        self.hLine_c = pg.InfiniteLine(angle=0, movable=False)
        self.p_c.addItem(self.vLine_c, ignoreBounds=True)
        self.p_c.addItem(self.hLine_c, ignoreBounds=True)

        # print('5')
        self.__colormap = colormap
        if labelColormap is None:
            labelColormap = self.defaultLabelColormap
        self.__labelColormap = labelColormap
        # vars updated in setWindow
        self.__window = [None, None]
        # vars updated in setImage
        # self.__image = sitk.ReadImage('B2_CESAG.dcm.nii')

        self.__image = None
        self.__label = None
        self.__ROI = None
        self.__ROIArray = None
        self.__ROISlice = None
        self.possy = None
        self.possx = None
        self.__imageArray = None
        self.__labelArray = None
        self.__z,self.__y, self.__x = None,None,None
        self.__cur_z,self.__cur_y,self.__cur_x = None,None,None
        self.__sagittal,self.__axial, self.__coronal = None,None,None
        self.__sagittal_label, self.__axial_label, self.__coronal_label = None, None, None
        self.__sagittal_pix, self.__axial_pix, self.__coronal_pix = None, None, None
        self.__direction = None
        self.__smoothMethod = None
        self.__smoothKernel = None

        # print('6')
        self.proxy_a = pg.SignalProxy(self.p_a.scene().sigMouseClicked, rateLimit=60, slot=self.mouseCliked)
        # zoom to fit imageo
        # p_a.autoRange()
        # self.p_a.disableAutoRange()
        self.p_a.setAspectLocked(lock=True, ratio=4)

        self.proxy_c = pg.SignalProxy(self.p_c.scene().sigMouseClicked, rateLimit=60, slot=self.mouseCliked)
        self.p_c.setAspectLocked(lock=True, ratio=4)
        # self.p_c.autoRange()

        self.proxy_s = pg.SignalProxy(self.p_s.scene().sigMouseClicked, rateLimit=60, slot=self.mouseCliked)
        # zoom to fit imageo
        # self.p_s.autoRange()

        # vars updated in setIndex
        # self.__index = 0
        # vars updated in setOpacity
        # print('7')
        self.__opacity = 1
        # execute param
        self.setWindow(window)

        if image is not None:
            self.setImage(image)
            # self.setIndex(index)
            if label is not None:
                self.setOpacity(opacity)
                self.setLabel(label)

    def mouseCliked(self, ev):
        # print(ev)
        # global cur_x, cur_y, cur_z, sagittal, coronal, axial
        pos = ev[0].scenePos()
        # print('clicked:',pos)
        # itemBoundingRect
        # if p_a.sceneBoundingRect().contains(pos):
        if self.p_a.sceneBoundingRect().contains(pos) and (self.__imageArray is not None):
            mousePoint = self.p_a.vb.mapSceneToView(pos)
            # print(mousePoint)
            if 0 <= mousePoint.x() < self.__z and 0 <= mousePoint.y() < self.__x:
                self.vLine_a.setPos(mousePoint.x())
                self.hLine_a.setPos(mousePoint.y())

                self.__cur_z = int(self.__z - mousePoint.x() + 0.5)
                self.__cur_x = int(self.__x - mousePoint.y() + 0.5)

                self.__sagittal = np.flipud(self.__imageArray[self.__cur_z, :, :])
                self.__coronal = np.fliplr(np.rot90(self.__imageArray[:, :, self.__cur_x], 1))
                # self.img_s.setImage(self.__sagittal)
                # self.img_c.setImage(self.__coronal)

                self.vLine_s.setPos(self.__cur_x)
                self.hLine_s.setPos(self.__y - self.__cur_y)
                self.vLine_c.setPos(self.__z - self.__cur_z)
                self.hLine_c.setPos(self.__y - self.__cur_y)

                # self.label.setText(
                #     "<span style='font-size: 12pt'>x=%d,   <span style='font-size: 12pt'>y=%d</span>, <span style='font-size: 12pt'>z=%d " % (
                #         self.__cur_x+1, self.__cur_y+1, self.__cur_z+1))
            # ev.accept()
        if self.p_s.sceneBoundingRect().contains(pos)and (self.__imageArray is not None):
            mousePoint = self.p_s.vb.mapSceneToView(pos)
            if 0 <= mousePoint.x() < self.__x and 0 <= mousePoint.y() < self.__y:

                self.vLine_s.setPos(mousePoint.x())
                self.hLine_s.setPos(mousePoint.y())

                self.__cur_x = int(mousePoint.x() + 0.5)
                self.__cur_y = int(self.__y - mousePoint.y() + 0.5)

                self.__axial = np.fliplr(np.rot90(self.__imageArray[:, self.__cur_y, :], 1))
                self.__coronal = np.fliplr(np.rot90(self.__imageArray[:, :, self.__cur_x], 1))

                # self.img_a.setImage(self.__axial)
                # self.img_c.setImage(self.__coronal)

                self.vLine_a.setPos(self.__z - self.__cur_z)
                self.hLine_a.setPos(self.__x - self.__cur_x)
                self.vLine_c.setPos(self.__z - self.__cur_z)
                self.hLine_c.setPos(self.__y - self.__cur_y)

                # self.label.setText(
                #     "<span style='font-size: 12pt'>x=%d,   <span style='font-size: 12pt'>y=%d</span>, <span style='font-size: 12pt'>z=%d " % (
                #         self.__cur_x+1, self.__cur_y+1, self.__cur_z+1))
        #
        if self.p_c.sceneBoundingRect().contains(pos)and (self.__imageArray is not None):
            mousePoint = self.p_c.vb.mapSceneToView(pos)
            if 0 <= mousePoint.x() < self.__z and 0 <= mousePoint.y() < self.__y:
                self.vLine_c.setPos(mousePoint.x())
                self.hLine_c.setPos(mousePoint.y())

                self.__cur_z = int(self.__z - mousePoint.x() + 0.5)
                self.__cur_y = int(self.__y - mousePoint.y() + 0.5)

                self.__axial = np.fliplr(np.rot90(self.__imageArray[:, self.__cur_y, :], 1))
                self.__sagittal = np.flipud(self.__imageArray[self.__cur_z, :, :])


                # self.img_a.setImage(self.__axial)
                # self.img_s.setImage(self.__sagittal)

                self.vLine_a.setPos(self.__z - self.__cur_z)
                self.hLine_a.setPos(self.__x - self.__cur_x)
                self.vLine_s.setPos(self.__cur_x)
                self.hLine_s.setPos(self.__y - self.__cur_y)

                # self.label.setText(
                #     "<span style='font-size: 12pt'>x=%d,   <span style='font-size: 12pt'>y=%d</span>, <span style='font-size: 12pt'>z=%d " % (
                #         self.__cur_x+1, self.__cur_y+1, self.__cur_z+1))

        # self.__updateLabelArray()
        self.__updateLabelMap()
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()

    def setImage(self, image):
        assert image.GetDimension() == 3, "accepts 3D image only"
        self.__image = image
        self.__label = None
        self.__ROI = None
        self.__index = 0
        self.__updateImageArray()
        self.__updateLabelArray()
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()

        # print('setImage:',np.shape(self.__axial),np.unique(self.__axial))

    def setLabel(self, label):
        if self.__image is None:
            return
        assert label.GetSize() == self.__image.GetSize()
        self.__label = label
        self.__updateLabelArray()
        self.__updateLabelMap()
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()

    def setROI(self,ax = 's',type='Poly'):
        if self.__image is None:
            return
        self.__ROIArray = np.zeros(self.__imageArray.shape)


        if ax =='S':
            self.__ROIAx = ax
            if type == 'Poly':
                points =  np.array([[np.shape(self.__sagittal)[0]//4,np.shape(self.__sagittal)[1]//4],
                                    [np.shape(self.__sagittal)[0] // 4, np.shape(self.__sagittal)[1] // 2],
                                    [np.shape(self.__sagittal)[0] // 2, np.shape(self.__sagittal)[1] // 2]]
                                   )
                self.__ROI = pg.PolyLineROI(points,closed=True)
            elif type=='Circle':
                self.__ROI = pg.EllipseROI([np.shape(self.__sagittal)[0] // 2, np.shape(self.__sagittal)[1] // 2], [np.shape(self.__sagittal)[0]//8,np.shape(self.__sagittal)[1]//8])
            else:
                self.__ROI = pg.RectROI([np.shape(self.__sagittal)[0] // 2, np.shape(self.__sagittal)[1] // 2], [np.shape(self.__sagittal)[0]//8,np.shape(self.__sagittal)[1]//8])

            self.p_s.addItem(self.__ROI)
            cols, rows = self.__sagittal.shape
            m = np.mgrid[:cols, :rows]
            self.possx = m[0, :, :]  # make the x pos array
            self.possy = m[1, :, :]  # make the y pos array
            self.possx.shape = cols, rows
            self.possy.shape = cols, rows
            self.__ROISlice = np.zeros(self.__sagittal.shape)

        if ax =='A':
            self.__ROIAx = ax
            if type == 'Poly':
                points = np.array([[np.shape(self.__axial)[1] // 4, np.shape(self.__axial)[0] // 4],
                                   [np.shape(self.__axial)[1] // 2, np.shape(self.__axial)[0] // 4],
                                   [np.shape(self.__axial)[1] // 2, np.shape(self.__axial)[0] // 2]]
                                  )
                self.__ROI = pg.PolyLineROI(points,closed=True)
            elif type=='Circle':
                self.__ROI = pg.EllipseROI([np.shape(self.__axial)[1] // 2, np.shape(self.__axial)[0] // 2], [np.shape(self.__axial)[1] // 8, np.shape(self.__axial)[0] // 8])
            else:
                self.__ROI = pg.RectROI([np.shape(self.__axial)[1] // 2, np.shape(self.__axial)[0] // 2], [np.shape(self.__axial)[1] // 8, np.shape(self.__axial)[0] // 8])

            self.p_a.addItem(self.__ROI)
            # print('add a!',points)
            cols, rows = self.__axial.shape
            m = np.mgrid[:cols, :rows]
            self.possx = m[0, :, :]  # make the x pos array
            self.possy = m[1, :, :]  # make the y pos array
            self.possx.shape = cols, rows
            self.possy.shape = cols, rows
            self.__ROISlice = np.zeros(self.__axial.shape)

        if ax =='C':
            self.__ROIAx = ax
            if type == 'Poly':
                points = np.array([[np.shape(self.__coronal)[1] // 4, np.shape(self.__coronal)[0] // 4],
                                   [np.shape(self.__coronal)[1] // 2, np.shape(self.__coronal)[0] // 4],
                                   [np.shape(self.__coronal)[1] // 2, np.shape(self.__coronal)[0] // 2]]
                                  )
                self.__ROI = pg.PolyLineROI(points,closed=True)
            elif type=='Circle':
                self.__ROI = pg.EllipseROI([np.shape(self.__coronal)[1] // 2, np.shape(self.__coronal)[0] // 2], [np.shape(self.__coronal)[1] // 8, np.shape(self.__coronal)[0] // 8])
            else:
                self.__ROI = pg.RectROI([np.shape(self.__coronal)[1] // 2, np.shape(self.__coronal)[0] // 2], [np.shape(self.__coronal)[1] // 8, np.shape(self.__coronal)[0] // 8])

            self.p_c.addItem(self.__ROI)
            cols, rows = self.__coronal.shape
            m = np.mgrid[:cols, :rows]
            self.possx = m[0, :, :]  # make the x pos array
            self.possy = m[1, :, :]  # make the y pos array
            self.possx.shape = cols, rows
            self.possy.shape = cols, rows
            self.__ROISlice = np.zeros(self.__coronal.shape)

    def accROI(self):
        if self.__ROI is None:
            return
        if self.__ROIAx=='S':
            mpossx = self.__ROI.getArrayRegion(self.possx, self.img_s).astype(int)
            mpossx = mpossx[np.nonzero(mpossx)]  # get the x pos from ROI
            mpossy = self.__ROI.getArrayRegion(self.possy, self.img_s).astype(int)
            mpossy = mpossy[np.nonzero(mpossy)]  # get the y pos from ROI
            self.__ROISlice[mpossx, mpossy] = self.__sagittal[mpossx, mpossy]
            self.__ROISlice = (self.__ROISlice>0).astype(int)
            self.__ROIArray[self.__cur_z, :, :] = np.flipud(self.__ROISlice)

            if self.__labelArray is not None:
                self.__labelArray += self.__ROIArray.astype(np.uint8)
            else:
                self.__labelArray = self.__ROIArray.astype(np.uint8)
            self.p_s.removeItem(self.__ROI)

        if self.__ROIAx=='A':
            mpossx = self.__ROI.getArrayRegion(self.possx, self.img_a).astype(int)
            mpossx = mpossx[np.nonzero(mpossx)]  # get the x pos from ROI
            mpossy = self.__ROI.getArrayRegion(self.possy, self.img_a).astype(int)
            mpossy = mpossy[np.nonzero(mpossy)]  # get the y pos from ROI
            self.__ROISlice[mpossx, mpossy] = self.__axial[mpossx, mpossy]
            self.__ROISlice = (self.__ROISlice>0).astype(int)
            self.__ROIArray[:, self.__cur_y, :] = np.fliplr(np.rot90((self.__ROISlice),1))
            # self.__ROIArray[:, self.__cur_y, :] = self.__ROISlice

            if self.__labelArray is not None:
                self.__labelArray += self.__ROIArray.astype(np.uint8)
            else:
                self.__labelArray = self.__ROIArray.astype(np.uint8)
            self.p_a.removeItem(self.__ROI)

        if self.__ROIAx=='C':
            mpossx = self.__ROI.getArrayRegion(self.possx, self.img_c).astype(int)
            mpossx = mpossx[np.nonzero(mpossx)]  # get the x pos from ROI
            mpossy = self.__ROI.getArrayRegion(self.possy, self.img_c).astype(int)
            mpossy = mpossy[np.nonzero(mpossy)]  # get the y pos from ROI
            self.__ROISlice[mpossx, mpossy] = self.__coronal[mpossx, mpossy]
            self.__ROISlice = (self.__ROISlice>0).astype(int)
            self.__ROIArray[:, :, self.__cur_x] = np.fliplr(np.rot90((self.__ROISlice),1))

            if self.__labelArray is not None:
                self.__labelArray += self.__ROIArray.astype(np.uint8)
            else:
                self.__labelArray = self.__ROIArray.astype(np.uint8)
            self.p_c.removeItem(self.__ROI)

        self.__updateLabelMap()
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()
        # print('1',np.unique(self.__labelArray))
        tmp = sitk.GetImageFromArray(self.__labelArray)
        tmp.SetDirection(self.__image.GetDirection())
        tmp.SetOrigin(self.__image.GetOrigin())
        tmp.SetSpacing(self.__image.GetSpacing())
        return tmp
            # np.flipud(self.__imageArray[self.__cur_z, :, :])

    def saveSelROI(self):
        # to be implemented
        if self.__ROIArray is not None:
            image_out = sitk.GetImageFromArray(self.__ROIArray)
            image_out.SetDirection(self.__image.GetDirection())
            image_out.SetOrigin(self.__image.GetOrigin())
            image_out.SetSpacing(self.__image.GetSpacing())
            sitk.WriteImage(image_out, 'sel_ROI.dcm.nii')
            print('save Sel!')
        return

    def saveAllROI(self):
        # to be implemented
        if self.__ROIArray is not None:
            # if self.__labelArray is not None:
            image_out = sitk.GetImageFromArray(self.__labelArray)
            image_out.SetDirection(self.__image.GetDirection())
            image_out.SetOrigin(self.__image.GetOrigin())
            image_out.SetSpacing(self.__image.GetSpacing())
            sitk.WriteImage(image_out, 'all_ROI.dcm.nii')
            # sitk.WriteImage(sitk.GetImageFromArray(self.__labelArray), 'mask.nii.gz')
            # else:
            #     sitk.WriteImage(sitk.GetImageFromArray(self.__ROIArray), 'mask.nii.gz')
            print('save All!')
        return


    def clrSelROI(self):
        # 什么时候都没有改变过Label
        self.__ROIArray = None
        self.__ROISlice = None
        self.__updateLabelArray() # 重新读取了原来的label的labelArray
        self.__updateLabelMap() # 更新各个面的label
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()
        if self.__ROIAx == 's':
            self.p_s.removeItem(self.__ROI)
        return

    def clrAllROI(self):
        self.__label = None
        self.__ROIArray = None
        self.__ROISlice = None
        self.__updateLabelArray() # 把各个面的label都清空了
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()
        return

    def denoise(self):
        if self.__imageArray is None:
            return
        self.__imageArray = denoise_wavelet(self.__imageArray, multichannel=False, rescale_sigma=True)
        minVal = self.__imageArray.min()

        maxVal = self.__imageArray.max()

        self.__imageArray = np.clip( \
                (self.__imageArray - np.float32(minVal))/np.float32(maxVal-minVal), 0, 1)
        self.__imageArray = (255*self.__imageArray).astype(np.uint8)
        # print(self.__imageArray.shape,self.__imageArray.min(),self.__imageArray.max())
        self.__updateImageMap()
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()
        # print('finish denoise!')
        return

    def setSmoothMethod(self,method):
        self.__smoothMethod = method
        return

    def setSmoothKernel(self,kernel_size):
        self.__smoothKernel = kernel_size
        return

    def clrProcess(self):
        self.__updateImageArray()
        self.__updateLabelArray()
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()
        return

    def smooth(self):
        # assume that the first axial is Saggittal
        if self.__imageArray is None:
            return
        if self.__smoothMethod =='Guassian':
            self.__imageArray = guassianSmooth(self.__imageArray,self.__smoothKernel)
        if self.__smoothMethod =='Mean':
            self.__imageArray = meanSmooth(self.__imageArray,self.__smoothKernel)
        if self.__smoothMethod =='Median':
            self.__imageArray = medianSmooth(self.__imageArray,self.__smoothKernel)
        self.__updateImageMap()
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()
        print('finish smooth!',self.__smoothKernel,self.__smoothMethod)
        return

    def resample(self,tuple):
        if self.__imageArray is None:
            return
        self.__labelArray = None
        self.__label = None
        self.__imageArray = transform.resize(self.__imageArray,tuple)
        self.__z,self.__y,self.__x = np.shape(self.__imageArray)
        self.__cur_z = self.__z // 2
        self.__cur_x = self.__x // 2
        self.__cur_y = self.__y // 2

        self.__sagittal = np.flipud(self.__imageArray[self.__z // 2, :, :])
        self.__axial = np.fliplr(np.rot90(self.__imageArray[:, self.__y // 2, :], 1))
        self.__coronal = np.fliplr(np.rot90(self.__imageArray[:, :, self.__x // 2], 1))
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()
        # print('resample!')

    def thredSeg(self, threshold):
        if self.__imageArray is None:
            return
        self.__labelArray = (self.__imageArray>threshold)*3
        self.__labelArray = self.__labelArray.astype(np.uint8)
        self.__updateLabelMap()
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()
        print('seg!')

    def setOpacity(self, opacity):
        assert opacity >=0 and opacity <=1, "opacity out of range"
        self.__opacity = opacity
        if self.__image is None or self.__label is None:
            return
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()

    def setWindow(self, window):
        self.__window = window
        if self.__image is None:
            return
        self.__updateImageArray()
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()

    def setColormap(self, colormap):
        self.__colormap = colormap
        if self.__image is None:
            return
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()

    def setLabelColormap(self, labelColormap):
        if labelColormap is None:
            labelColormap = self.defaultLabelColormap
        self.__labelColormap = labelColormap
        if self.__image is None or self.__label is None:
            return
        self.__updatePixmapS()
        self.__updatePixmapA()
        self.__updatePixmapC()

    def __updateImageArray(self):
        array = sitk.GetArrayFromImage(self.__image)
        if self.__window[0] is None:
            minVal = array.min()
        else:
            minVal = self.__window[0]
        if self.__window[1] is None:
            maxVal = array.max()
        else:
            maxVal = self.__window[1]
        self.__imageArray = np.clip( \
                (array - np.float32(minVal))/np.float32(maxVal-minVal), 0, 1)
        self.__imageArray = (255*self.__imageArray).astype(np.uint8)

        self.__z,self.__y,self.__x = np.shape(self.__imageArray)
        self.__cur_z = self.__z // 2
        self.__cur_x = self.__x // 2
        self.__cur_y = self.__y // 2

        self.__sagittal = np.flipud(self.__imageArray[self.__z // 2, :, :])
        self.__axial = np.fliplr(np.rot90(self.__imageArray[:, self.__y // 2, :], 1))
        self.__coronal = np.fliplr(np.rot90(self.__imageArray[:, :, self.__x // 2], 1))
        # print(self.__z,self.__y,self.__x )
        # print(np.shape(self.__sagittal),np.unique(self.__sagittal))

    def __updateImageMap(self):
        if self.__imageArray is not None:
            self.__sagittal = np.flipud(self.__imageArray[self.__cur_z, :, :])
            self.__axial = np.fliplr(np.rot90(self.__imageArray[:, self.__cur_y , :], 1))
            self.__coronal = np.fliplr(np.rot90(self.__imageArray[:, :, self.__cur_x ], 1))


    def __updateLabelArray(self):
        if self.__label is None:
            self.__labelArray = None
            self.__sagittal_label = None
            self.__axial_label = None
            self.__coronal_label = None
        else:
            array = sitk.GetArrayFromImage(self.__label)

            self.__labelArray = array.astype(np.uint8)
            # minVal = array.min()
            # maxVal = array.max()
            # self.__labelArray = (array - np.float32(minVal))/np.float32(maxVal-minVal)
            # self.__labelArray = (255*self.__labelArray).astype(np.uint8)

    def __updateLabelMap(self):
        if self.__labelArray is not None:
            self.__sagittal_label = np.flipud(self.__labelArray[self.__cur_z, :, :])
            self.__axial_label = np.fliplr(np.rot90(self.__labelArray[:, self.__cur_y, :], 1))
            self.__coronal_label = np.fliplr(np.rot90(self.__labelArray[:, :, self.__cur_x ], 1))
            # print('update label:',np.unique(self.__sagittal_label),)
            # print('cur:',self.__cur_x,self.__cur_y,self.__cur_z)

    def __updatePixmapS(self):
        image = self.__sagittal
        if self.__colormap is None:
            image = np.stack([image, image, image], axis=-1)
        else:
            image = cv2.applyColorMap(image, self.__colormap)# 3d image?
        if self.__labelArray is not None:
            label = self.__sagittal_label
            # self.__opacity = 0.5
            # print(label,np.shape(label),np.unique(label),np.sum(label==5))
            if self.__labelColormap.shape[-1] == 4:
                alphaMap = self.__labelColormap[:,:,-1].reshape(256,1,1)
            else:
                alphaMap = np.array([0]+[255]*255, \
                        dtype=np.uint8).reshape(256,1,1)
            labelColormap = self.__labelColormap[:,:,0:3]
            alpha = cv2.applyColorMap(label, alphaMap).astype(np.float32)/255
            alpha = alpha * self.__opacity
            label = cv2.applyColorMap(label, labelColormap).astype(np.float32)
            array = image*(1-alpha)+label*alpha
            self.__sagittal_pix = array.astype(np.uint8)
        else:
            self.__sagittal_pix = image
        self.img_s.setImage(self.__sagittal_pix)
        self.p_s.autoRange()

    def __updatePixmapA(self):
        image = self.__axial
        if self.__colormap is None:
            image = np.stack([image, image, image], axis=-1)
        else:
            image = cv2.applyColorMap(image, self.__colormap)# 3d image?
        if self.__labelArray is not None:
            label = self.__axial_label
            if self.__labelColormap.shape[-1] == 4:
                alphaMap = self.__labelColormap[:,:,-1].reshape(256,1,1)
            else:
                alphaMap = np.array([0]+[255]*255, \
                        dtype=np.uint8).reshape(256,1,1)
            labelColormap = self.__labelColormap[:,:,0:3]
            alpha = cv2.applyColorMap(label, alphaMap).astype(np.float32)/255
            alpha = alpha * self.__opacity
            label = cv2.applyColorMap(label, labelColormap).astype(np.float32)
            array = image*(1-alpha)+label*alpha
            self.__axial_pix = array.astype(np.uint8)
        else:
            self.__axial_pix = image

    def __updatePixmapC(self):
        image = self.__coronal
        if self.__colormap is None:
            image = np.stack([image, image, image], axis=-1)
        else:
            image = cv2.applyColorMap(image, self.__colormap)# 3d image?
        if self.__labelArray is not None:
            label = self.__coronal_label
            if self.__labelColormap.shape[-1] == 4:
                alphaMap = self.__labelColormap[:,:,-1].reshape(256,1,1)
            else:
                alphaMap = np.array([0]+[255]*255, \
                        dtype=np.uint8).reshape(256,1,1)
            labelColormap = self.__labelColormap[:,:,0:3]
            alpha = cv2.applyColorMap(label, alphaMap).astype(np.float32)/255
            alpha = alpha * self.__opacity
            label = cv2.applyColorMap(label, labelColormap).astype(np.float32)
            array = image*(1-alpha)+label*alpha
            self.__coronal_pix = array.astype(np.uint8)
        else:
            self.__coronal_pix = image
        self.img_s.setImage(self.__sagittal_pix)
        self.img_a.setImage(self.__axial_pix)
        self.img_c.setImage(self.__coronal_pix)
        # if self.__sagittal_label is not None:
        #     print(np.unique(self.__sagittal_label))
        # else:
        #     print('None')
        self.p_s.autoRange()
        self.p_a.autoRange()
        self.p_c.autoRange()
        self.label.setText(
            "<span style='font-size: 12pt'>x=%d,   <span style='font-size: 12pt'>y=%d</span>, <span style='font-size: 12pt'>z=%d " % (
                self.__cur_x+1, self.__cur_y+1, self.__cur_z+1))
    #     array = array[:,:,::-1]
        # img = QImage(array.copy().data, \
        #         array.shape[1], array.shape[0], QImage.Format_RGB888)
        # pixmap = QPixmap.fromImage(img)
        # self.setPixmap(pixmap)

class SliderWithTextWidget(QWidget):
    def __init__(self, parent=None, text=None):
        super(SliderWithTextWidget, self).__init__(parent)
        if text is not None:
            self.labelText = QLabel(self)
            self.labelText.setText(str(text))
        self.labelIndex = QLabel(self)
        self.labelIndex.setText('1/1')
        self.sliderIndex = QSlider(Qt.Horizontal, self)
        self.sliderIndex.setMaximum(1)
        self.sliderIndex.setMinimum(1)
        self.sliderIndex.setValue(1)
        hbox = QHBoxLayout(self)
        if text is not None:
            hbox.addWidget(self.labelText)
        hbox.addWidget(self.sliderIndex)
        hbox.addWidget(self.labelIndex)
        self.sliderIndex.valueChanged.connect(self.__slotIndexChanged)
        self.setMinimum = self.sliderIndex.setMinimum
        self.setValue = self.sliderIndex.setValue
        self.value = self.sliderIndex.value
        self.valueChanged = self.sliderIndex.valueChanged

    def setMaximum(self, *args, **kw):
        self.sliderIndex.setMaximum(*args, **kw)
        self.labelIndex.setText( \
                str(self.sliderIndex.value())+ \
                '/'+str(self.sliderIndex.maximum()))

    @pyqtSlot(int)
    def __slotIndexChanged(self, index):
        self.labelIndex.setText(str(index)+'/'+str(self.sliderIndex.maximum()))
        #self.sliderIndex.setSliderPosition(self.__visibleIndex + 1)


class SpinBoxWithTextWidget(QWidget):
    def __init__(self, parent=None, text=None):
        super(SpinBoxWithTextWidget, self).__init__(parent)
        if text is not None:
            self.labelText = QLabel(self)
            self.labelText.setText(str(text))

        hbox = QHBoxLayout(self)
        if text is not None:
            hbox.addWidget(self.labelText)

        self.sp=QSpinBox()
        hbox.addWidget(self.sp)
        # self.sp.valueChanged.connect(self.Valuechange)
        self.btnApply = QPushButton('Apply')
        hbox.addWidget(self.btnApply)
        self.btnClr = QPushButton('Clear')
        hbox.addWidget(self.btnClr)

class resampleWidget(QWidget):
    def __init__(self, parent=None, text='Resample'):
        super(resampleWidget, self).__init__(parent)
        if text is not None:
            self.labelText = QLabel(self)
            self.labelText.setText(str(text))

        hbox = QHBoxLayout(self)
        if text is not None:
            hbox.addWidget(self.labelText)

        self.label_x = QLabel(self)
        self.label_x.setText('size_x')
        self.label_y = QLabel(self)
        self.label_y.setText('size_y')
        self.label_z = QLabel(self)
        self.label_z.setText('size_z')

        self.sp_x = QSpinBox()
        self.sp_x.setMaximum(2000)
        self.sp_x.setMinimum(1)
        self.sp_y = QSpinBox()
        self.sp_y.setMaximum(2000)
        self.sp_y.setMinimum(1)
        self.sp_z = QSpinBox()
        self.sp_z.setMaximum(2000)
        self.sp_z.setMinimum(1)
        hbox.addWidget(self.label_x)
        hbox.addWidget(self.sp_x)
        hbox.addWidget(self.label_y)
        hbox.addWidget(self.sp_y)
        hbox.addWidget(self.label_z)
        hbox.addWidget(self.sp_z)
        # self.sp.valueChanged.connect(self.Valuechange)
        self.btnApply = QPushButton('Apply')

        hbox.addWidget(self.btnApply)


class volumeViewerWidget(QWidget):
    displayPercentile = 0.001
    opacityMax = 100
    indexMouseRightScale = 1/16
    def __init__(self, parent=None, colormap=None):
        super(volumeViewerWidget, self).__init__(parent)
        self.sliderOpacity = SliderWithTextWidget(self, text='Opacity')
        # self.sliderGuassian   = SliderWithTextWidget(self, text=' Guassian  ')
        self.viewerSlice =  volumeSliceViewerWidget(self, colormap=colormap)
        self.GaussianBox = SpinBoxWithTextWidget(self, text=' Kernel Size')
        self.ThredBox = SpinBoxWithTextWidget(self, text='Threshold Segmentation')
        self.ResampleBox = resampleWidget(self, text='Resample')

        self.ThredBox.sp.setMaximum(1000)

        vbox = QVBoxLayout(self)
        vbox.addWidget(self.viewerSlice, stretch=1)
        # vbox.addWidget(self.sliderIndex)
        vbox.addWidget(self.sliderOpacity)
        vbox.addWidget(self.GaussianBox)
        vbox.addWidget(self.ResampleBox)
        vbox.addWidget(self.ThredBox)

        self.sliderOpacity.setMinimum(0)
        self.sliderOpacity.setMaximum(self.opacityMax)
        self.sliderOpacity.setValue(self.opacityMax)
        self.sliderOpacity.hide()

        self.GaussianBox.hide()
        self.ResampleBox.hide()
        self.ThredBox.hide()

        self.__mouseRightPressing = False
        self.__mouseRightPos = QPoint(0,0)
        self.__mouseRightIndex = 0
        
        # self.sliderIndex.valueChanged.connect(\
        #         lambda x: self.viewerSlice.setIndex(x-1))
        self.sliderOpacity.valueChanged.connect(\
                lambda x: self.viewerSlice.setOpacity(x/self.opacityMax))

        self.GaussianBox.btnApply.clicked.connect(self.viewerSlice.smooth)
        self.GaussianBox.btnClr.clicked.connect(self.viewerSlice.clrProcess)
        self.GaussianBox.sp.valueChanged.connect(self.smoothChange)


        self.__resampleX = None
        self.__resampleY = None
        self.__resampleZ = None

        self.ResampleBox.sp_x.valueChanged.connect(self.resampleChangeX)
        self.ResampleBox.sp_y.valueChanged.connect(self.resampleChangeY)
        self.ResampleBox.sp_z.valueChanged.connect(self.resampleChangeZ)

        self.ResampleBox.btnApply.clicked.connect(self.resample)

        self.ThredBox.btnApply.clicked.connect(self.thredSeg)

    def smoothChange(self):
        self.viewerSlice.setSmoothKernel(self.GaussianBox.sp.value())

    def thredSeg(self):
        self.viewerSlice.thredSeg(self.ThredBox.sp.value())

    def resampleChangeX(self,size):
        self.__resampleX = size

    def resampleChangeY(self,size):
        self.__resampleY = size

    def resampleChangeZ(self,size):
        self.__resampleZ = size

    def resample(self):
        self.viewerSlice.resample((self.__resampleZ,self.__resampleY, self.__resampleX))

    def setImage(self, image):
        imageArray = sitk.GetArrayFromImage(image)
        minVal = np.percentile(imageArray.ravel(), \
                self.displayPercentile*100)
        maxVal = np.percentile(imageArray.ravel(), \
                (1 - self.displayPercentile)*100)
        self.viewerSlice.setImage(image)
        self.viewerSlice.setWindow([minVal, maxVal])
        # self.sliderIndex.setMinimum(1)
        # self.sliderIndex.setMaximum(imageArray.shape[0])
        self.sliderOpacity.hide()

    def setLabel(self, label):
        labelArray = sitk.GetArrayFromImage(label)
        self.viewerSlice.setLabel(label)
        self.sliderOpacity.show()

    def setPreprocessMethod(self,method = 'Gaussian'):
        if method =='Median':
            self.GaussianBox.labelText.setText(method + str(' Kernel Size(odd)'))
            self.viewerSlice.setSmoothMethod(method)
            self.GaussianBox.show()
        elif method =='Resample':
            self.ResampleBox.show()
        else:
            self.GaussianBox.labelText.setText(method+str(' Kernel Size'))
            self.viewerSlice.setSmoothMethod(method)
            self.GaussianBox.show()

    def setSegMethod(self,method = 'Threshold'):
        if method =='Threshold':
            self.ThredBox.show()


    def setROI(self,ax = 's',type='Poly'):
        self.viewerSlice.setROI(ax,type)

    def accROI(self):
        tmp = self.viewerSlice.accROI()
        return tmp

    def saveSelROI(self):
        self.viewerSlice.saveSelROI()

    def saveAllROI(self):
        self.viewerSlice.saveAllROI()

    def clrSelROI(self):
        self.viewerSlice.clrSelROI()

    def clrAllROI(self):
        self.viewerSlice.clrAllROI()

    def denoise(self):
        self.viewerSlice.denoise()


    def mousePressEvent(self, event):
        if (event.button() == Qt.RightButton):
            self.__mouseRightPressing = True
            self.__mouseRightPressPos = event.pos()
            # self.__mouseRightIndex = self.sliderIndex.value()
        else:
            super(volumeViewerWidget, self).mousePressEvent(event)
            
    def mouseMoveEvent(self, event):
        if self.__mouseRightPressing and (event.buttons() & Qt.RightButton):
            currentPos = event.pos()
            delta = currentPos - self.__mouseRightPressPos
            # self.sliderIndex.setValue( \
            #         round(delta.y()*self.indexMouseRightScale) + \
            #         self.__mouseRightIndex)
        else:
            super(volumeViewerWidget, self).mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if (event.button() == Qt.RightButton):
            self.__mouseRightPressing = False
        else:
            super(volumeViewerWidget, self).mouseReleaseEvent(event)

if __name__ == '__main__':
    import sys, os, time
    from PyQt5.QtWidgets import QApplication
    from ReadSagittalPD import ReadSagittalPDs
    # dicomPath='/mnt/repo/privateData/cartilage_origin/FromXuhua/PD/A102747075'
    #dicomPath=sys.argv[1]
    image = sitk.ReadImage('B2_CESAG.dcm.nii')
    label = sitk.ReadImage('B2_Label.nii')
    # image = sitk.GetArrayFromImage(image)
    #image = ReadSagittalPDs(dicomPath)[0]
    # label = sitk.ReadImage('')
    # flipped = sitk.Flip(label, (False, False, True), True)
    # flipped = sitk.GetImageFromArray(\
    #         (sitk.GetArrayFromImage(label)[:,::-1,:]).astype(np.uint8))
    # flipped.CopyInformation(label)
    # app = QApplication(sys.argv)
    # ex = volumeSliceViewerWidget()
    # #ex = volumeViewerWidget(colormap = cv2.COLORMAP_SPRING)
    # # ex = volumeViewerWidget()
    # #ex = SliderWithTextWidget(text="TEXT")
    # # ex.setGeometry(300, 300, 600, 600)
    # # ex.setWindowTitle('volumeViewerWidget')
    # ex.show()
    # time.sleep(1)
    # ex.setImage(image)
    # time.sleep(1)
    # #ex.setLabel(flipped)
    # sys.exit(app.exec_())

    app = QApplication(sys.argv)
    app.setStyle(QtGui.QStyleFactory.create("Cleanlooks"))

    image_widget = volumeViewerWidget()
    image_widget.show()
    image_widget.setImage(image)
    image_widget.setLabel(label)

    import sys
    if (sys.flags.interactive != 1) or not hasattr(QtCore,     'PYQT_VERSION'):
        QtGui.QApplication.instance().exec_()