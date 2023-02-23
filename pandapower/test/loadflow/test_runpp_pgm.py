from unittest.mock import patch, MagicMock

import pytest

import pandapower as pp
from pandapower.test.consistency_checks import runpp_pgm_with_consistency_checks


def test_minimal_net_pgm():
    # tests corner-case when the grid only has 1 bus and an ext-grid
    net = pp.create_empty_network()
    b = pp.create_bus(net, 110)
    pp.create_ext_grid(net, b)
    runpp_pgm_with_consistency_checks(net)

    pp.create_load(net, b, p_mw=0.1)
    runpp_pgm_with_consistency_checks(net)

    b2 = pp.create_bus(net, 110)
    pp.create_switch(net, b, b2, 'b')
    pp.create_sgen(net, b2, p_mw=0.2)
    runpp_pgm_with_consistency_checks(net)


def test_runpp_pgm__invalid_algorithm():
    net = pp.create_empty_network()
    with pytest.raises(KeyError, match="Invalid algorithm 'foo'; choose from: 'nr' (newton_raphson), 'lin' (linear), "
                                       "'bfsw' (iterative_current), 'lc' (linear_current)"):
        pp.runpp_pgm(net, algorithm="foo")


def test_runpp_pgm__asym():
    net = pp.create_empty_network()
    with pytest.raises(NotImplementedError, match="Asymmetric power flow by power-grid-model is not implemented yet"):
        pp.runpp_pgm(net, symmetric=False)


@patch("pandapower.run.logger")
def test_runpp_pgm__internal_pgm_error(mock_logger: MagicMock):
    net = pp.create_empty_network()
    b1 = pp.create_bus(net, 110)
    pp.create_ext_grid(net, b1, vm_pu=1)
    b2 = pp.create_bus(net, 50)
    pp.create_line(net, b1, b2, 1, std_type="NAYY 4x50 SE")
    pp.runpp_pgm(net)

    assert net["converged"] is False
    mock_logger.critical.assert_called_once_with("Internal PowerGridError occurred!")
    mock_logger.debug.assert_called_once()
    mock_logger.info.assert_called_once_with("Use validate_input=True to validate your input data.")


@patch("pandapower.run.logger")
def test_runpp_pgm__validation_fail(mock_logger: MagicMock):
    net = pp.create_empty_network()
    pp.create_bus(net, -110, index=123)
    pp.runpp_pgm(net, validate_input=True)

    mock_logger.error.assert_called_once_with("1. Power Grid Model validation error: Check bus-123")
    mock_logger.debug.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
