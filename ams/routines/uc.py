"""
Real-time economic dispatch.
"""
import logging
from collections import OrderedDict
import numpy as np
import pandas as pd

from ams.core.param import RParam
from ams.core.service import NumOp, ZonalSum, NumHstack, NumOpDual
from ams.routines.ed import EDData, EDModel

from ams.opt.omodel import Var, Constraint, Objective

logger = logging.getLogger(__name__)


class UCData(EDData):
    """
    UC data.
    """

    def __init__(self):
        EDData.__init__(self)
        self.csu = RParam(info='startup cost',
                          name='csu', tex_name=r'c_{su}',
                          model='GCost', src='csu',
                          unit='$',)
        self.csd = RParam(info='shutdown cost',
                          name='csd', tex_name=r'c_{sd}',
                          model='GCost', src='csd',
                          unit='$',)
        self.td1 = RParam(info='minimum ON duration',
                          name='td1', tex_name=r't_{d1}',
                          model='StaticGen', src='td1',
                          unit='min',)
        self.td2 = RParam(info='minimum OFF duration',
                          name='td2', tex_name=r't_{d2}',
                          model='StaticGen', src='td2',
                          unit='min',)

        self.sd.info = 'zonal load factor for UC'
        self.sd.model = 'UCTSlot'

        self.timeslot.info = 'Time slot for multi-period UC'
        self.timeslot.model = 'UCTSlot'

        self.dt = RParam(info='UC interval',
                         name='dt', tex_name=r't{d}',
                         model='UCTSlot', src='dt',
                         unit='min',)

        self.dnsrp = RParam(info='non-spinning reserve requirement in percentage',
                            name='dnsr', tex_name=r'd_{nsr}',
                            model='NSR', src='demand',
                            unit='%',)

        self.Sn = RParam(info='generator capacity',
                         name='Sn', src='Sn',
                         tex_name=r'S_{n}', unit='MW',
                         model='StaticGen',)


class UCModel(EDModel):
    """
    UC model.
    """

    def __init__(self, system, config):
        EDModel.__init__(self, system, config)
        self.info = 'unit commitment'
        self.type = 'DCUC'
        # --- vars ---
        self.ugd = Var(info='commitment decision',
                       horizon=self.timeslot,
                       name='ugd', tex_name=r'u_{g,d}',
                       model='StaticGen', src='u',
                       boolean=True,)
        self.vgd = Var(info='startup action',
                       horizon=self.timeslot,
                       name='vgd', tex_name=r'v_{g,d}',
                       model='StaticGen', src='u',
                       boolean=True,)
        self.wgd = Var(info='shutdown action',
                       horizon=self.timeslot,
                       name='wgd', tex_name=r'w_{g,d}',
                       model='StaticGen', src='u',
                       boolean=True,)

        self.zug = Var(info='Aux var for ugd',
                       horizon=self.timeslot,
                       name='zug', tex_name=r'z_{ug}',
                       model='StaticGen', pos=True,)

        # NOTE: actions have two parts, one for initial status, another for the rest
        self.actv = Constraint(name='actv', type='eq',
                               info='startup action',
                               e_str='ugd @ Mr - vgd[:, 1:]',)
        self.actv0 = Constraint(name='actv0', type='eq',
                                info='initial startup action',
                                e_str='ugd[:, 0] - ug  - vgd[:, 0]',)
        self.actw = Constraint(name='actw', type='eq',
                               info='shutdown action',
                               e_str='-ugd @ Mr - wgd[:, 1:]',)
        self.actw0 = Constraint(name='actw0', type='eq',
                                info='initial shutdown action',
                                e_str='-ugd[:, 0] + ug - wgd[:, 0]',)

        # --- constraints ---
        self.pb.e_str = 'pds - gs @ zug'  # power balance

        # --- big M for ugd*pg ---
        self.Mzug = NumOp(info='10 times of max of pmax as big M for zug',
                          name='Mzug', tex_name=r'M_{zug}',
                          u=self.pmax, fun=np.max,
                          rfun=np.dot, rargs=dict(b=10),)
        self.zuglb = Constraint(name='zuglb', info='zug lower bound',
                                type='uq', e_str='- zug + pg')
        self.zugub = Constraint(name='zugub', info='zug upper bound',
                                type='uq', e_str='zug - pg - Mzug[0] * (1 - ugd)')
        self.zugub2 = Constraint(name='zugub2', info='zug upper bound',
                                 type='uq', e_str='zug - Mzug[0] * ugd')

        # --- reserve ---
        # 1) non-spinning reserve
        self.dnsrpz = NumOpDual(u=self.pdz, u2=self.dnsrp, fun=np.multiply,
                                name='dnsrpz', tex_name=r'd_{nsr, p, z}',
                                info='zonal non-spinning reserve requirement in percentage',)
        self.dnsr = NumOpDual(u=self.dnsrpz, u2=self.sd, fun=np.multiply,
                              rfun=np.transpose,
                              name='dnsr', tex_name=r'd_{nsr}',
                              info='zonal non-spinning reserve requirement',)
        self.nsr = Constraint(name='nsr', info='non-spinning reserve', type='uq',
                              e_str='-gs@(multiply((1 - ugd), Rpmax)) + dnsr')
        # 2) spinning reserve
        self.dsrpz = NumOpDual(u=self.pdz, u2=self.dsrp, fun=np.multiply,
                               name='dsrpz', tex_name=r'd_{sr, p, z}',
                               info='zonal spinning reserve requirement in percentage',)
        self.dsr = NumOpDual(u=self.dsrpz, u2=self.sd, fun=np.multiply,
                             rfun=np.transpose,
                             name='dsr', tex_name=r'd_{sr}',
                             info='zonal spinning reserve requirement',)
        self.sr = Constraint(name='sr', info='spinning reserve', type='uq',
                             e_str='gs@(zug - multiply(Rpmax, ugd)) + dsr')

        # TODO: constrs: minimum ON/OFF time for conventional units
        # TODO: add data prameters: minimum ON/OFF time for conventional units

        # TODO: constrs: unserved energy constraint

        # self.rgu = Constraint(name='rgu',
        #                       info='ramp up limit of generator output',
        #                       e_str='pg - pg0 - R10',
        #                       type='uq',
        #                       )
        # self.rgd = Constraint(name='rgd',
        #                       info='ramp down limit of generator output',
        #                       e_str='-pg + pg0 - R10',
        #                       type='uq',
        #                       )
        # --- objective ---
        # NOTE: havn't adjust time duration
        gcost = 'sum(c2 * zug**2 + c1 * zug + c0 * ugd + csu * vgd + csd * wgd)'
        rcost = ''
        self.obj.e_str = gcost + rcost

    def _initial_guess(self):
        """
        Make initial guess for commitment decision.
        """
        # NOTE: make guess for commitment decision
        # check trigger condition
        ug0 = self.system.PV.get(src='u', attr='v', idx=self.system.PV.idx.v)
        if (ug0 == 0).any():
            return True
        else:
            logger.warning('All generators are online at initial, make initial guess for commitment.')

        gen = pd.DataFrame()
        gen['idx'] = self.system.PV.idx.v
        gen['Sn'] = self.system.PV.get(src='Sn', attr='v', idx=gen['idx'])
        gen['bus'] = self.system.PV.get(src='bus', attr='v', idx=gen['idx'])
        gen['zone'] = self.system.PV.get(src='zone', attr='v', idx=gen['idx'])
        gcost_idx = self.system.GCost.find_idx(keys='gen', values=gen['idx'])
        gen['c2'] = self.system.GCost.get(src='c2', attr='v', idx=gcost_idx)
        gen['c1'] = self.system.GCost.get(src='c1', attr='v', idx=gcost_idx)
        gen['c0'] = self.system.GCost.get(src='c0', attr='v', idx=gcost_idx)
        gen['wsum'] = 0.4*gen['c2'] + 0.3*gen['c1'] + 0.2*gen['c0'] + 0.1*gen['Sn']
        gen = gen.sort_values(by='wsum', ascending=True)

        # Turn off 30% of the generators as initial guess
        priority = gen['idx'].values
        g_idx = priority[0:int(0.3*len(priority))]
        self.system.StaticGen.set(src='u', attr='v', idx=g_idx,
                                  value=np.zeros_like(g_idx))
        logger.warning(f'Turn off StaticGen {g_idx} as initial guess for commitment.')
        return True

    def init(self, **kwargs):
        self._initial_guess()
        super().init(**kwargs)


class UC(UCData, UCModel):
    """
    DC-based unit commitment (UC), wherew.

    References
    ----------
    1. Huang, Y., Pardalos, P. M., & Zheng, Q. P. (2017). Electrical power unit commitment: deterministic and
    two-stage stochastic programming models and algorithms. Springer.

    2. D. A. Tejada-Arango, S. Lumbreras, P. Sánchez-Martín and A. Ramos, "Which Unit-Commitment Formulation
    is Best? A Comparison Framework," in IEEE Transactions on Power Systems, vol. 35, no. 4, pp. 2926-2936,
    July 2020, doi: 10.1109/TPWRS.2019.2962024.
    """

    def __init__(self, system, config):
        UCData.__init__(self)
        UCModel.__init__(self, system, config)
