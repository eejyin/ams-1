# Copyright (c) 1996-2015 PSERC. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

"""Runs an optimal power flow.
"""

import logging

from os.path import dirname, join

from ams.solver.pypower.ppoption import ppoption
from ams.solver.pypower.opf import opf
from ams.solver.pypower.printpf import printpf
from ams.solver.pypower.savecase import savecase


def runopf(casedata=None, ppopt=None, fname='', solvedcase=''):
    """Runs an optimal power flow.

    @see: L{rundcopf}, L{runuopf}

    @author: Ray Zimmerman (PSERC Cornell)
    """
    ## default arguments
    if casedata is None:
        casedata = join(dirname(__file__), 'case9')
    ppopt = ppoption(ppopt)

    ##-----  run the optimal power flow  -----
    r = opf(casedata, ppopt)

    ##-----  output results  -----
    if fname:
        fd = None
        try:
            fd = open(fname, "a")
        except IOError as detail:
            logger.debug("Error opening %s: %s.\n" % (fname, detail))
        finally:
            if fd is not None:
                printpf(r, fd, ppopt)
                fd.close()

    else:
        # printpf(r, stdout, ppopt)
        pass

    ## save solved case
    if solvedcase:
        savecase(solvedcase, r)

    return r


if __name__ == '__main__':
    ppopt = ppoption(OPF_ALG=580)
    runopf(None, ppopt)