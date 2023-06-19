"""
Base class for parameters.
"""


import logging

from typing import Callable, Iterable, List, Optional, Tuple, Type, Union
from collections import OrderedDict

import numpy as np

from andes.core.common import Config
from andes.core import BaseParam, DataParam, IdxParam, NumParam, ExtParam
from andes.models.group import GroupBase

from ams.core.var import Algeb

logger = logging.getLogger(__name__)


class RParam:
    """
    Class for parameters in a routine.

    This class is an extension of conventional parameters
    `BaseParam`, `DataParam`, `IdxParam`, and `NumParam`.
    It contains a `group` attribute to indicate the group.
    """

    def __init__(self,
                 name: Optional[str] = None,
                 tex_name: Optional[str] = None,
                 info: Optional[str] = None,
                 src: Optional[str] = None,
                 unit: Optional[str] = None,
                 owner_name: Optional[str] = None,
                 v: Optional[np.ndarray] = None,
                 v_str: Optional[str] = None,
                 ):

        self.name = name
        self.tex_name = tex_name if (tex_name is not None) else name
        self.info = info
        self.src = name if (src is None) else src
        self.unit = unit
        self.is_group = False
        self.owner_name = owner_name  # indicate if this variable is a group variable
        self.owner = None  # instance of the owner model or group
        self.is_set = False  # indicate if the value is set externally
        self.v_str = v_str
        if v is not None:
            self._v = v
            self.is_set = True

    @property
    def v(self):
        """
        Return the value of the parameter.

        This property is a wrapper of the `get` method.
        """
        if self.is_set:
            return self._v
        elif self.is_group:
            return self.owner.get(src=self.src, attr='v',
                                  idx=self.owner.get_idx())
        else:
            src_param = getattr(self.owner, self.src)
            return getattr(src_param, 'v')

    @property
    def n(self):
        if self.is_set:
            return self._v.shape[0]
        else:
            return self.owner.n

    @property
    def class_name(self):
        """
        Return the class name
        """
        return self.__class__.__name__

    def __repr__(self):
        if self.is_set:
            span = ''
            if self.v.ndim == 1:
                if len(self.v) <= 20:
                    span = f', v={self.v}'
            else:
                span = f', v=shape{self.v.shape}'
            return f'{self.__class__.__name__}: {self.name}{span}'
        else:
            span = ''
            if 1 <= self.n <= 20:
                span = f', v={self.v}'
                if hasattr(self, 'vin') and (self.vin is not None):
                    span += f', vin={self.vin}'

            if self.v.ndim == 1:
                if len(self.v) <= 20:
                    span = f', v={self.v}'
            else:
                span = f', v=shape{self.v.shape}'

            return f'{self.__class__.__name__}: {self.owner.__class__.__name__}.{self.name}{span}'

    def get_idx(self):
        if self.is_group:
            return self.owner.get_idx()
        elif self.owner is None:
            logger.info(f'Param <{self.name}> has no owner.')
            return None
        else:
            return self.owner.idx.v
