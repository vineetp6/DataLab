# -*- coding: utf-8 -*-
#
# Licensed under the terms of the BSD 3-Clause
# (see cdl/LICENSE for details)

"""
DataLab Datasets
"""

# pylint: disable=invalid-name  # Allows short reference names like x, y, ...
# pylint: disable=duplicate-code

from __future__ import annotations

import enum
import re
from collections.abc import ByteString, Iterator, Mapping, Sequence
from copy import deepcopy
from typing import TYPE_CHECKING, Any

import guidata.dataset.dataitems as gdi
import guidata.dataset.datatypes as gdt
import numpy as np
from guidata.configtools import get_icon
from guidata.utils import update_dataset
from guiqwt.annotations import AnnotatedCircle, AnnotatedRectangle
from guiqwt.builder import make
from guiqwt.image import MaskedImageItem
from numpy import ma
from skimage import draw

from cdl.config import Conf, _
from cdl.core.computation.image import scale_data_to_min_max
from cdl.core.model import base

if TYPE_CHECKING:  # pragma: no cover
    from qtpy import QtWidgets as QW


def make_roi_rectangle(
    x0: int, y0: int, x1: int, y1: int, title: str
) -> AnnotatedRectangle:
    """Make and return the annnotated rectangle associated to ROI

    Args:
        x0 (int): top left corner X coordinate
        y0 (int): top left corner Y coordinate
        x1 (int): bottom right corner X coordinate
        y1 (int): bottom right corner Y coordinate
        title (str): title
    """
    roi_item: AnnotatedRectangle = make.annotated_rectangle(x0, y0, x1, y1, title)
    param = roi_item.label.labelparam
    param.anchor = "BL"
    param.xc, param.yc = 5, -5
    param.update_label(roi_item.label)
    return roi_item


def make_roi_circle(x0: int, y0: int, x1: int, y1: int, title: str) -> AnnotatedCircle:
    """Make and return the annnotated circle associated to ROI

    Args:
        x0 (int): top left corner X coordinate
        y0 (int): top left corner Y coordinate
        x1 (int): bottom right corner X coordinate
        y1 (int): bottom right corner Y coordinate
        title (str): title
    """
    item = AnnotatedCircle(x0, y0, x1, y1)
    item.annotationparam.title = title
    item.annotationparam.update_annotation(item)
    item.set_style("plot", "shape/drag")
    return item


def to_builtin(obj) -> str | int | float | list | dict | np.ndarray | None:
    """Convert an object implementing a numeric value or collection
    into the corresponding builtin/NumPy type.

    Return None if conversion fails."""
    try:
        return int(obj) if int(obj) == float(obj) else float(obj)
    except (TypeError, ValueError):
        pass
    if isinstance(obj, ByteString):
        return str(obj)
    if isinstance(obj, Sequence):
        return str(obj) if len(obj) == len(str(obj)) else list(obj)
    if isinstance(obj, Mapping):
        return dict(obj)
    if isinstance(obj, np.ndarray):
        return obj
    return None


class RoiDataGeometries(enum.Enum):
    """ROI data geometry types"""

    RECTANGLE = 0
    CIRCLE = 1


class RoiDataItem:
    """Object representing an image ROI.

    Args:
        data (numpy.ndarray | list | tuple): ROI data
    """

    def __init__(self, data: np.ndarray | list | tuple):
        self._data = data

    @classmethod
    def from_image(cls, obj, geometry: RoiDataGeometries) -> RoiDataItem:
        """Construct roi data item from image object: called for making new ROI items

        Args:
            obj (ImageObj): image object
            geometry (RoiDataGeometries): ROI geometry
        """
        x0, x1 = obj.x0, obj.size[0] + obj.x0
        if geometry is RoiDataGeometries.RECTANGLE:
            y0, y1 = obj.y0, obj.size[1] + obj.y0
        else:
            y0 = y1 = 0.5 * (2 * obj.y0 + obj.size[1])
        coords = x0, y0, x1, y1
        return cls(coords)

    @property
    def geometry(self) -> RoiDataGeometries:
        """ROI geometry"""
        _x0, y0, _x1, y1 = self._data
        if y0 == y1:
            return RoiDataGeometries.CIRCLE
        return RoiDataGeometries.RECTANGLE

    def get_rect(self) -> tuple[int, int, int, int]:
        """Get rectangle coordinates"""
        x0, y0, x1, y1 = self._data
        if self.geometry is RoiDataGeometries.CIRCLE:
            y0 -= x1 - x0
            y1 += x1 - x0
        return x0, y0, x1, y1

    def get_masked_view(self, data: np.ndarray, maskdata: np.ndarray) -> np.ndarray:
        """Return masked view for data

        Args:
            data (numpy.ndarray): data
            maskdata (numpy.ndarray): mask data
        """
        x0, y0, x1, y1 = self.get_rect()
        masked_view = data.view(ma.MaskedArray)
        masked_view.mask = maskdata
        return masked_view[y0:y1, x0:x1]

    def apply_mask(self, data: np.ndarray, yxratio: float) -> np.ndarray:
        """Apply ROI to data as a mask and return masked array

        Args:
            data (numpy.ndarray): data
            yxratio (float): Y/X ratio
        """
        roi_mask = np.ones_like(data, dtype=bool)
        x0, y0, x1, y1 = self.get_rect()
        if self.geometry is RoiDataGeometries.RECTANGLE:
            roi_mask[y0:y1, x0:x1] = False
        else:
            xc, yc = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
            radius = 0.5 * (x1 - x0)
            rr, cc = draw.ellipse(yc, xc, radius / yxratio, radius, shape=data.shape)
            roi_mask[rr, cc] = False
        return roi_mask

    def make_roi_item(
        self, index: int | None, fmt: str, lbl: bool, editable: bool = True
    ):
        """Make ROI plot item

        Args:
            index (int | None): ROI index
            fmt (str): format string
            lbl (bool): if True, show label
            editable (bool): if True, ROI is editable
        """
        coords = self._data
        if self.geometry is RoiDataGeometries.RECTANGLE:
            func = make_roi_rectangle
        else:
            func = make_roi_circle
        title = "ROI" if index is None else f"ROI{index:02d}"
        return base.make_roi_item(func, coords, title, fmt, lbl, editable)


class ImageObj(gdt.DataSet, base.ObjectItf):
    """Image dataset

    Args:
        title (str): title
        comment (str): comment
        icon (str): icon
    """

    PREFIX = "i"
    CONF_FMT = Conf.view.ima_format
    DEFAULT_FMT = ".1f"
    VALID_DTYPES = (
        np.uint8,
        np.uint16,
        np.int16,
        np.int32,
        np.float32,
        np.float64,
        np.complex128,
    )

    def __init__(self, title=None, comment=None, icon=""):
        gdt.DataSet.__init__(self, title, comment, icon)
        base.ObjectItf.__init__(self)
        self._dicom_template = None
        self._maskdata_cache = None

    @property
    def size(self) -> tuple[int, int]:
        """Returns (width, height)"""
        return self.data.shape[1], self.data.shape[0]

    def __add_metadata(self, key: str, value: Any) -> None:
        """Add value to metadata if value can be converted into builtin/NumPy type

        Args:
            key (str): key
            value (Any): value
        """
        stored_val = to_builtin(value)
        if stored_val is not None:
            self.metadata[key] = stored_val

    def reset_metadata_to_defaults(self) -> None:
        """Reset metadata to default values"""
        base.ObjectItf.reset_metadata_to_defaults(self)
        # Default visualization settings
        for name, opt in (
            ("colormap", Conf.view.ima_def_colormap),
            ("interpolation", Conf.view.ima_def_interpolation),
        ):
            defval = opt.get(None)
            if defval is not None:
                self.metadata[name] = defval
        # TODO: [P2] Add default signal/image visualization settings
        # 1. Add signal visualization settings?
        # 2. Add more image visualization settings?
        # 3. Add a dialog box to edit default settings in main window
        #    (use a guidata dataset with only a selection of items from guiqwt.styles
        #     classes)
        # 4. Update all active objects when settings were changed

    def set_metadata_from(self, obj: Mapping | dict) -> None:
        """Set metadata from object: dict-like (only string keys are considered)
        or any other object (iterating over supported attributes)

        Args:
            obj (Mapping | dict): object
        """
        self.reset_metadata_to_defaults()
        ptn = r"__[\S_]*__$"
        if isinstance(obj, Mapping):
            for key, value in obj.items():
                if isinstance(key, str) and not re.match(ptn, key):
                    self.__add_metadata(key, value)
        else:
            for attrname in dir(obj):
                if attrname != "GroupLength" and not re.match(ptn, attrname):
                    try:
                        attr = getattr(obj, attrname)
                        if not callable(attr) and attr:
                            self.__add_metadata(attrname, attr)
                    except AttributeError:
                        pass

    @property
    def dicom_template(self):
        """Get DICOM template"""
        return self._dicom_template

    @dicom_template.setter
    def dicom_template(self, template):
        """Set DICOM template"""
        if template is not None:
            ipp = getattr(template, "ImagePositionPatient", None)
            if ipp is not None:
                self.x0, self.y0 = float(ipp[0]), float(ipp[1])
            pxs = getattr(template, "PixelSpacing", None)
            if pxs is not None:
                self.dy, self.dx = float(pxs[0]), float(pxs[1])
            self.set_metadata_from(template)
            self._dicom_template = template

    _tabs = gdt.BeginTabGroup("all")

    _datag = gdt.BeginGroup(_("Data and metadata"))
    data = gdi.FloatArrayItem(_("Data"))
    metadata = base.MetadataItem(_("Metadata"), default={})
    _e_datag = gdt.EndGroup(_("Data and metadata"))

    _dxdyg = gdt.BeginGroup(_("Origin and pixel spacing"))
    _origin = gdt.BeginGroup(_("Origin"))
    x0 = gdi.FloatItem("X<sub>0</sub>", default=0.0)
    y0 = gdi.FloatItem("Y<sub>0</sub>", default=0.0).set_pos(col=1)
    _e_origin = gdt.EndGroup(_("Origin"))
    _pixel_spacing = gdt.BeginGroup(_("Pixel spacing"))
    dx = gdi.FloatItem("Δx", default=1.0, nonzero=True)
    dy = gdi.FloatItem("Δy", default=1.0, nonzero=True).set_pos(col=1)
    _e_pixel_spacing = gdt.EndGroup(_("Pixel spacing"))
    _e_dxdyg = gdt.EndGroup(_("Origin and pixel spacing"))

    _unitsg = gdt.BeginGroup(_("Titles and units"))
    title = gdi.StringItem(_("Image title"), default=_("Untitled"))
    _tabs_u = gdt.BeginTabGroup("units")
    _unitsx = gdt.BeginGroup(_("X-axis"))
    xlabel = gdi.StringItem(_("Title"), default="")
    xunit = gdi.StringItem(_("Unit"), default="")
    _e_unitsx = gdt.EndGroup(_("X-axis"))
    _unitsy = gdt.BeginGroup(_("Y-axis"))
    ylabel = gdi.StringItem(_("Title"), default="")
    yunit = gdi.StringItem(_("Unit"), default="")
    _e_unitsy = gdt.EndGroup(_("Y-axis"))
    _unitsz = gdt.BeginGroup(_("Z-axis"))
    zlabel = gdi.StringItem(_("Title"), default="")
    zunit = gdi.StringItem(_("Unit"), default="")
    _e_unitsz = gdt.EndGroup(_("Z-axis"))
    _e_tabs_u = gdt.EndTabGroup("units")
    _e_unitsg = gdt.EndGroup(_("Titles and units"))

    _e_tabs = gdt.EndTabGroup("all")

    @property
    def xc(self) -> float:
        """Return image center X-axis coordinate"""
        return self.x0 + 0.5 * self.data.shape[1] * self.dx

    @property
    def yc(self) -> float:
        """Return image center Y-axis coordinate"""
        return self.y0 + 0.5 * self.data.shape[0] * self.dy

    def get_data(self, roi_index: int | None = None) -> np.ndarray:
        """
        Return original data (if ROI is not defined or `roi_index` is None),
        or ROI data (if both ROI and `roi_index` are defined).

        Args:
            roi_index (int): ROI index

        Returns:
            numpy.ndarray: masked data
        """
        if self.roi is None or roi_index is None:
            return self.data
        roidataitem = RoiDataItem(self.roi[roi_index])
        return roidataitem.get_masked_view(self.data, self.maskdata)

    def copy_data_from(self, other: ImageObj, dtype: np.dtype | None = None) -> None:
        """Copy data from other dataset instance.

        Args:
            other (ImageObj): other dataset instance
            dtype (numpy.dtype | None): data type
        """
        self.x0 = other.x0
        self.y0 = other.y0
        self.dx = other.dx
        self.dy = other.dy
        self.metadata = deepcopy(other.metadata)
        self.data = np.array(other.data, copy=True, dtype=dtype)
        self.dicom_template = other.dicom_template

    def set_data_type(self, dtype: np.dtype) -> None:
        """Change data type.

        Args:
            dtype (numpy.dtype): data type
        """
        self.data = np.array(self.data, dtype=dtype)

    def __viewable_data(self) -> np.ndarray:
        """Return viewable data"""
        data = self.data.real
        if np.any(np.isnan(data)):
            data = np.nan_to_num(data, posinf=0, neginf=0)
        return data

    def __update_item_params(self, item: MaskedImageItem) -> None:
        """Update plot item parameters

        Args:
            item (MaskedImageItem): plot item
        """
        for axis in ("x", "y", "z"):
            unit = getattr(self, axis + "unit")
            fmt = r"%.1f"
            if unit:
                fmt = r"%.1f (" + unit + ")"
            setattr(item.imageparam, axis + "format", fmt)
        # Updating origin and pixel spacing
        has_origin = self.x0 is not None and self.y0 is not None
        has_pixelspacing = self.dx is not None and self.dy is not None
        if has_origin or has_pixelspacing:
            x0, y0, dx, dy = 0.0, 0.0, 1.0, 1.0
            if has_origin:
                x0, y0 = self.x0, self.y0
            if has_pixelspacing:
                dx, dy = self.dx, self.dy
            shape = self.data.shape
            item.imageparam.xmin, item.imageparam.xmax = x0, x0 + dx * shape[1]
            item.imageparam.ymin, item.imageparam.ymax = y0, y0 + dy * shape[0]
        update_dataset(item.imageparam, self.metadata)
        item.imageparam.update_image(item)

    def make_item(self, update_from: MaskedImageItem | None = None) -> MaskedImageItem:
        """Make plot item from data.

        Args:
            update_from (MaskedImageItem | None): update from plot item

        Returns:
            MaskedImageItem: plot item
        """
        data = self.__viewable_data()
        item = make.maskedimage(
            data,
            self.maskdata,
            title=self.title,
            colormap="jet",
            eliminate_outliers=Conf.view.ima_eliminate_outliers.get(0.1),
            interpolation="nearest",
            show_mask=True,
        )
        if update_from is None:
            self.__update_item_params(item)
        else:
            update_dataset(item.imageparam, update_from.imageparam)
            item.imageparam.update_image(item)
        return item

    def update_item(self, item: MaskedImageItem, data_changed: bool = True) -> None:
        """Update plot item from data.

        Args:
            item (MaskedImageItem): plot item
            data_changed (bool): if True, data has changed
        """
        if data_changed:
            item.set_data(self.__viewable_data(), lut_range=[item.min, item.max])
        item.set_mask(self.maskdata)
        item.imageparam.label = self.title
        self.__update_item_params(item)
        item.plot().update_colormap_axis(item)

    def get_roi_param(self, title, *defaults) -> gdt.DataSet:
        """Return ROI parameters dataset.

        Args:
            title (str): title
            *defaults: default values
        """
        roidataitem = RoiDataItem(defaults)

        xd0, yd0, xd1, yd1 = defaults

        def s(name: str, index: int):
            """Returns name<sub>index</sub>"""
            return f"{name}<sub>{index}</sub>"

        if roidataitem.geometry is RoiDataGeometries.RECTANGLE:
            gtitle1 = _("Top left corner")
            gtitle2 = _("Bottom right corner")

            class ROIParam(gdt.DataSet):
                """ROI parameters"""

                geometry = roidataitem.geometry

                def get_suffix(self):
                    """Get suffix text representation for ROI extraction"""
                    return f"x={self.x0}:{self.x1},y={self.y0}:{self.y1}"

                def get_coords(self):
                    """Get ROI coordinates"""
                    return self.x0, self.y0, self.x1, self.y1

                _tlcorner = gdt.BeginGroup(gtitle1)
                x0 = gdi.IntItem(s("X", 0), default=xd0, unit="pixel")
                y0 = gdi.IntItem(s("Y", 0), default=yd0, unit="pixel").set_pos(1)
                _e_tlcorner = gdt.EndGroup(gtitle1)
                _brcorner = gdt.BeginGroup(gtitle2)
                x1 = gdi.IntItem(s("X", 1), default=xd1, unit="pixel")
                y1 = gdi.IntItem(s("Y", 1), default=yd1, unit="pixel").set_pos(1)
                _e_brcorner = gdt.EndGroup(gtitle2)

        else:
            gtitle1 = _("Center coordinates")

            class ROIParam(gdt.DataSet):
                """ROI parameters"""

                geometry = roidataitem.geometry

                def get_single_roi(self):
                    """Get single circular ROI, i.e. after extracting ROI from image"""
                    return np.array([(0, self.r, self.x1 - self.x0, self.r)], int)

                def get_suffix(self):
                    """Get suffix text representation for ROI extraction"""
                    return f"xc={self.xc},yc={self.yc},r={self.r}"

                def get_coords(self):
                    """Get ROI coordinates"""
                    return self.x0, self.yc, self.x1, self.yc

                @property
                def x0(self):
                    """Return rectangle top left corner X coordinate"""
                    return self.xc - self.r

                @property
                def x1(self):
                    """Return rectangle bottom right corner X coordinate"""
                    return self.xc + self.r

                @property
                def y0(self):
                    """Return rectangle top left corner Y coordinate"""
                    return self.yc - self.r

                @property
                def y1(self):
                    """Return rectangle bottom right corner Y coordinate"""
                    return self.yc + self.r

                _tlcorner = gdt.BeginGroup(gtitle1)
                xc = gdi.IntItem(
                    s("X", "C"), default=int(0.5 * (xd0 + xd1)), unit="pixel"
                )
                yc = gdi.IntItem(s("Y", "C"), default=yd0, unit="pixel").set_pos(1)
                _e_tlcorner = gdt.EndGroup(gtitle1)
                r = gdi.IntItem(
                    _("Radius"), default=int(0.5 * (xd1 - xd0)), unit="pixel"
                )

        return ROIParam(title)

    @staticmethod
    def params_to_roidata(params: gdt.DataSetGroup) -> np.ndarray | None:
        """Convert ROI dataset group to ROI array data.

        Args:
            params (DataSetGroup): ROI dataset group

        Returns:
            numpy.ndarray: ROI array data
        """
        roilist = []
        for roiparam in params.datasets:
            roilist.append(roiparam.get_coords())
        if len(roilist) == 0:
            return None
        return np.array(roilist, int)

    def new_roi_item(
        self, fmt: str, lbl: bool, editable: bool, geometry: RoiDataGeometries
    ) -> MaskedImageItem:
        """Return a new ROI item from scratch

        Args:
            fmt (str): format string
            lbl (bool): if True, add label
            editable (bool): if True, ROI is editable
            geometry (RoiDataGeometries): ROI geometry
        """
        roidataitem = RoiDataItem.from_image(self, geometry)
        return roidataitem.make_roi_item(None, fmt, lbl, editable)

    def roi_coords_to_indexes(self, coords: list) -> np.ndarray:
        """Convert ROI coordinates to indexes.

        Args:
            coords (list): coordinates

        Returns:
            numpy.ndarray: indexes
        """
        indexes = np.array(coords)
        if indexes.size > 0:
            indexes[:, ::2] -= self.x0 + 0.5 * self.dx
            indexes[:, ::2] /= self.dx
            indexes[:, 1::2] -= self.y0 + 0.5 * self.dy
            indexes[:, 1::2] /= self.dy
        return np.array(indexes, int)

    def iterate_roi_items(self, fmt: str, lbl: bool, editable: bool = True) -> Iterator:
        """Make plot item representing a Region of Interest.

        Args:
            fmt (str): format string
            lbl (bool): if True, add label
            editable (bool): if True, ROI is editable

        Yields:
            PlotItem: plot item
        """
        if self.roi is not None:
            roicoords = np.array(self.roi, float)
            roicoords[:, ::2] *= self.dx
            roicoords[:, ::2] += self.x0 - 0.5 * self.dx
            roicoords[:, 1::2] *= self.dy
            roicoords[:, 1::2] += self.y0 - 0.5 * self.dy
            for index, coords in enumerate(roicoords):
                roidataitem = RoiDataItem(coords)
                yield roidataitem.make_roi_item(index, fmt, lbl, editable)

    @property
    def maskdata(self) -> np.ndarray:
        """Return masked data (areas outside defined regions of interest)

        Returns:
            numpy.ndarray: masked data
        """
        roi_changed = self.roi_has_changed()
        if self.roi is None:
            if roi_changed:
                self._maskdata_cache = None
        elif roi_changed or self._maskdata_cache is None:
            mask = np.ones_like(self.data, dtype=bool)
            for roirow in self.roi:
                roidataitem = RoiDataItem(roirow)
                roi_mask = roidataitem.apply_mask(self.data, yxratio=self.dy / self.dx)
                mask &= roi_mask
            self._maskdata_cache = mask
        return self._maskdata_cache

    def invalidate_maskdata_cache(self) -> None:
        """Invalidate mask data cache: force to rebuild it"""
        self._maskdata_cache = None


def create_image(
    title: str,
    data: np.ndarray | None = None,
    metadata: dict | None = None,
    units: tuple | None = None,
    labels: tuple | None = None,
) -> ImageObj:
    """Create a new Image object

    Args:
        title (str): image title
        data (numpy.ndarray): image data
        metadata (dict): image metadata
        units (tuple): X, Y, Z units (tuple of strings)
        labels (tuple): X, Y, Z labels (tuple of strings)

    Returns:
        ImageObj: image object
    """
    assert isinstance(title, str)
    assert data is None or isinstance(data, np.ndarray)
    image = ImageObj()
    image.title = title
    image.data = data
    if units is not None:
        image.xunit, image.yunit, image.zunit = units
    if labels is not None:
        image.xlabel, image.ylabel, image.zlabel = labels
    if metadata is None:
        image.reset_metadata_to_defaults()
    else:
        image.metadata = metadata
    return image


class ImageDatatypes(base.Choices):
    """Image data types"""

    @classmethod
    def from_dtype(cls, dtype):
        """Return member from NumPy dtype"""
        return getattr(cls, str(dtype).upper(), cls.UINT8)

    @classmethod
    def check(cls):
        """Check if data types are valid"""
        for member in cls:
            assert hasattr(np, member.value)

    UINT8 = enum.auto()
    UINT16 = enum.auto()
    INT16 = enum.auto()
    FLOAT32 = enum.auto()
    FLOAT64 = enum.auto()


ImageDatatypes.check()


class ImageTypes(base.Choices):
    """Image types"""

    ZEROS = _("zeros")
    EMPTY = _("empty")
    GAUSS = _("gaussian")
    UNIFORMRANDOM = _("random (uniform law)")
    NORMALRANDOM = _("random (normal law)")


class NewImageParam(gdt.DataSet):
    """New image dataset"""

    title = gdi.StringItem(_("Title"))
    height = gdi.IntItem(
        _("Height"), help=_("Image height (total number of rows)"), min=1, default=500
    )
    width = gdi.IntItem(
        _("Width"), help=_("Image width (total number of columns)"), min=1, default=500
    )
    dtype = gdi.ChoiceItem(
        _("Data type"), ImageDatatypes.get_choices(), default=ImageDatatypes.UINT16
    )
    type = gdi.ChoiceItem(_("Type"), ImageTypes.get_choices())


DEFAULT_TITLE = _("Untitled image")


def new_image_param(
    title: str | None = None,
    itype: ImageTypes | None = None,
    height: int | None = None,
    width: int | None = None,
    dtype: ImageDatatypes | None = None,
) -> NewImageParam:
    """Create a new Image dataset instance.

    Args:
        title (str): dataset title (default: None, uses default title)
        itype (ImageTypes): image type (default: None, uses default type)
        height (int): image height (default: None, uses default height)
        width (int): image width (default: None, uses default width)
        dtype (ImageDatatypes): image data type (default: None, uses default data type)

    Returns:
        NewImageParam: new image dataset instance
    """
    title = DEFAULT_TITLE if title is None else title
    param = NewImageParam(title=title, icon=get_icon("new_image.svg"))
    param.title = title
    if height is not None:
        param.height = height
    if width is not None:
        param.width = width
    if dtype is not None:
        param.dtype = dtype
    if itype is not None:
        param.type = itype
    return param


IMG_NB = 0


class Gauss2DParam(gdt.DataSet):
    """2D Gaussian parameters"""

    a = gdi.FloatItem("Norm")
    xmin = gdi.FloatItem("Xmin", default=-10).set_pos(col=1)
    sigma = gdi.FloatItem("σ", default=1.0)
    xmax = gdi.FloatItem("Xmax", default=10).set_pos(col=1)
    mu = gdi.FloatItem("μ", default=0.0)
    ymin = gdi.FloatItem("Ymin", default=-10).set_pos(col=1)
    x0 = gdi.FloatItem("X0", default=0)
    ymax = gdi.FloatItem("Ymax", default=10).set_pos(col=1)
    y0 = gdi.FloatItem("Y0", default=0).set_pos(col=0, colspan=1)


def create_image_from_param(
    newparam: NewImageParam,
    addparam: gdt.DataSet | None = None,
    edit: bool = False,
    parent: QW.QWidget | None = None,
) -> ImageObj | None:
    """Create a new Image object from dialog box.

    Args:
        newparam (NewImageParam): new image parameters
        addparam (DataSet): additional parameters
        edit (bool): Open a dialog box to edit parameters (default: False)
        parent (QWidget): parent widget

    Returns:
        ImageObj: new image object or None if user cancelled
    """
    global IMG_NB  # pylint: disable=global-statement
    if newparam is None:
        newparam = new_image_param()
    incr_sig_nb = not newparam.title
    if incr_sig_nb:
        newparam.title = f"{newparam.title} {IMG_NB + 1:d}"
    if not edit or addparam is not None or newparam.edit(parent=parent):
        prefix = newparam.type.name.lower()
        if incr_sig_nb:
            IMG_NB += 1
        image = create_image(newparam.title)
        shape = (newparam.height, newparam.width)
        dtype = newparam.dtype.value
        p = addparam
        if newparam.type == ImageTypes.ZEROS:
            image.data = np.zeros(shape, dtype=dtype)
        elif newparam.type == ImageTypes.EMPTY:
            image.data = np.empty(shape, dtype=dtype)
        elif newparam.type == ImageTypes.GAUSS:
            if p is None:
                p = Gauss2DParam(_("2D-gaussian image"))
            if p.a is None:
                try:
                    p.a = np.iinfo(dtype).max / 2.0
                except ValueError:
                    p.a = 10.0
            if edit and not p.edit(parent=parent):
                return None
            x, y = np.meshgrid(
                np.linspace(p.xmin, p.xmax, shape[1]),
                np.linspace(p.ymin, p.ymax, shape[0]),
            )
            zgauss = p.a * np.exp(
                -((np.sqrt((x - p.x0) ** 2 + (y - p.y0) ** 2) - p.mu) ** 2)
                / (2.0 * p.sigma**2)
            )
            image.data = np.array(zgauss, dtype=dtype)
            if image.title == DEFAULT_TITLE:
                image.title = (
                    f"{prefix}(a={p.a:g},μ={p.mu:g},σ={p.sigma:g}),"
                    f"x0={p.x0:g},y0={p.y0:g})"
                )
        elif newparam.type in (ImageTypes.UNIFORMRANDOM, ImageTypes.NORMALRANDOM):
            pclass = {
                ImageTypes.UNIFORMRANDOM: base.UniformRandomParam,
                ImageTypes.NORMALRANDOM: base.NormalRandomParam,
            }[newparam.type]
            if p is None:
                p = pclass(_("Image") + " - " + newparam.type.value)
                p.set_from_datatype(dtype)
            if edit and not p.edit(parent=parent):
                return None
            rng = np.random.default_rng(p.seed)
            if newparam.type == ImageTypes.UNIFORMRANDOM:
                data = rng.random(shape)
                image.data = scale_data_to_min_max(data, p.vmin, p.vmax)
                if image.title == DEFAULT_TITLE:
                    image.title = (
                        f"{prefix}(vmin={p.vmin:g},vmax={p.vmax:g},seed={p.seed})"
                    )
            elif newparam.type == ImageTypes.NORMALRANDOM:
                image.data = rng.normal(p.mu, p.sigma, size=shape)
                if image.title == DEFAULT_TITLE:
                    image.title = f"{prefix}(μ={p.mu:g},σ={p.sigma:g},seed={p.seed})"
            else:
                raise NotImplementedError(f"New param type: {newparam.type.value}")
        return image
    return None
