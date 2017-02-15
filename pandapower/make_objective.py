# -*- coding: utf-8 -*-

# Copyright (c) 2016 by University of Kassel and Fraunhofer Institute for Wind Energy and Energy
# System Technology (IWES), Kassel. All rights reserved. Use of this source code is governed by a
# BSD-style license that can be found in the LICENSE file.

import numpy as np
import warnings

from pypower.idx_brch import T_BUS, F_BUS
from pypower.idx_bus import BUS_TYPE, REF
from pandas import DataFrame
from scipy import sparse

from pandapower.pypower_extensions.makeYbus_pypower import makeYbus


def _make_objective(ppci, net, is_elems, cost_function="linear", lambda_opf=1, **kwargs):
    """
    Implementaton of diverse objective functions for the OPF of the Form C{N}, C{fparm},
    C{H} and C{Cw}

    INPUT:
        **ppci** - Matpower case of the net

    OPTIONAL:

        **objectivetype** (string, "linear") - string with name of objective function

            - **"linear"** - Linear costs of the form  :math:`I\\cdot P_G`. :math:`P_G` represents
              the active power values of the generators. Target of this objectivefunction is to
              maximize the generator output.
              This then basically is this:

                  .. math::
                      max\{P_G\}

            - **"linear_minloss"** - Quadratic costs of the form
              :math:`I\\cdot P_G - dV_m^T Y_L dV_m`.
              :math:`P_G` represents the active power values of the generators,
              :math:`dV_m` the voltage drop for each line and :math:`Y_L` the line admittance
              matrix.
              Target of this objectivefunction is to maximize the generator output but minimize the
              linelosses.
              This then basically is this:

                  .. math::
                      max\{P_G - dVm^TY_{L}dVm\}

            .. note:: Both objective functions have the following constraints:

                .. math::
                    V_{m,min} < &V_m < V_{m,max}\\\\
                    P_{G,min} < &P_G < P_{G,max}\\\\
                    Q_{G,min} < &Q_G < Q_{G,max}\\\\
                    I < &I_{max}

        **net** (attrdict, None) - Pandapower network

    """
    
    eg_idx = net._pd2ppc_lookups["ext_grid"] if "ext_grid" in net._pd2ppc_lookups else None
    gen_idx = net._pd2ppc_lookups["gen"] if "gen" in net._pd2ppc_lookups else None
    sgen_idx = net._pd2ppc_lookups["sgen_controllable"] if "sgen_controllable" in \
                    net._pd2ppc_lookups else None
    load_idx = net._pd2ppc_lookups["load_controllable"] if "load_controllable" in \
                    net._pd2ppc_lookups else None
    
    gen_costs = np.ones(len(ppci["gen"]))
    if eg_idx is not None and "cost_per_kw" in is_elems["ext_grid"]:
        gen_costs[eg_idx[is_elems["ext_grid"].index]] = is_elems["ext_grid"].cost_per_kw
    if gen_idx is not None and "cost_per_kw" in is_elems["gen"]:
        gen_costs[gen_idx[is_elems["gen"].index]] = is_elems["gen"].cost_per_kw
    if sgen_idx is not None and "cost_per_kw" in is_elems["sgen_controllable"]:
        gen_costs[sgen_idx[is_elems["sgen_controllable"].index]] = is_elems["sgen_controllable"].cost_per_kw
    if load_idx is not None and "cost_per_kw" in is_elems["load_controllable"]:
        gen_costs[load_idx[is_elems["load_controllable"].index]] = is_elems["load_controllable"].cost_per_kw
    
    ng = len(ppci["gen"])  # -
    nref = sum(ppci["bus"][:, BUS_TYPE] == REF)
#    if len(net.dcline) > 0:
#        gen_is = net.gen[net.gen.in_service==True]
#    else:
#        gen_is = is_elems['gen']

    if cost_function == "linear":

        ppci["gencost"] = np.zeros((ng, 8), dtype=float)
        ppci["gencost"][:nref, :] = np.array([1, 0, 0, 2, 0, 0, 1, 1]) # initializing gencost array for eg
        ppci["gencost"][nref:ng, :] = np.array([1, 0, 0, 2, 0, 0, 1, 0])  # initializing gencost array
        ppci["gencost"][:, 7] = np.nan_to_num(gen_costs*1e3)


    if cost_function == "linear_minloss":

        ppci["gencost"] = np.zeros((ng, 8), dtype=float)
        ppci["gencost"][:nref, :] = np.array([1, 0, 0, 2, 0, 0, 1, 1]) # initializing gencost array for eg
        ppci["gencost"][nref:ng, :] = np.array([1, 0, 0, 2, 0, 0, 1, 0])  # initializing gencost array
        ppci["gencost"][:, 7] = np.nan_to_num(gen_costs*1e3)

        # Get additional counts
        nb = len(ppci["bus"])
        nl = len(ppci["branch"])
        dim = 2 * nb + 2 * ng + 2 * nl

        # Get branch admitance matrices
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            Ybus, Yf, Yt = makeYbus(1, ppci["bus"], ppci["branch"])

        #########################
        # Additional z variables
        #########################

        # z_k = u_i - u_j
        # z_m = alpha_i - alpha_j
        # with i,j = start and endbus from lines

        # Epsilon for z constraints
        eps = 0

        # z constraints upper and lower bounds
        l = np.ones(2*nl)*eps
        u = np.ones(2*nl)*-eps

        # Initialize A and H matrix
        H = sparse.csr_matrix((dim, dim), dtype=float)
        A = sparse.csr_matrix((2*nl, dim), dtype=float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for i in range(nl):
                bus_f = int(ppci["branch"][i, F_BUS].real)
                bus_t = int(ppci["branch"][i, T_BUS].real)
                # minimization of potential difference between two buses
                H[dim-2*nl+i, dim-2*nl+i] = abs(Ybus[bus_f, bus_t]) * lambda_opf  # weigthing of minloss # NICHT BESSER REALTEIL?
                A[i, nb+bus_f] = 1
                A[i, nb+bus_t] = -1
                A[i, dim-2*nl+i] = 1
                # minimization of angle between two buses
                H[dim-nl+i, dim-nl+i] = abs(Ybus[bus_f, bus_t])# * 800 * lambda_opf  # weigthing of angles
                A[nl+i, bus_f] = 1
                A[nl+i, bus_t] = -1
                A[nl+i, dim-nl+i] = 1

        # Linear transformation for new omega-vector
        N = sparse.lil_matrix((dim, dim), dtype=float)
        for i in range(dim - 2*nl, dim):
            N[i, i] = 1.0

        # Cw = 0, no linear costs in additional costfunction
        Cw = np.zeros(dim, dtype=float)
        # d = 1
        d = np.ones((dim, 1), dtype=float)
        # r = 0
        r = np.zeros((dim, 1), dtype=float)
        # k = 0
        k = np.zeros((dim, 1), dtype=float)
        # m = 1
        m = np.ones((dim, 1), dtype=float)

        # Set ppci matrices
        ppci["H"] = H
        ppci["Cw"] = Cw
        ppci["N"] = N
        ppci["A"] = A
        ppci["l"] = l
        ppci["u"] = u
        ppci["fparm"] = np.hstack((d, r, k, m))

    return ppci