from functools import partial

import jax
import numpy as np
import pytest

from parsmooth._base import FunctionalModel, MVNParams
from parsmooth.linearization import extended, cubature
from parsmooth.sequential._filter import _sqrt_predict, _standard_predict, _sqrt_update, _standard_update, filtering
from tests._lgssm import get_data, transition_function as lgssm_f, observation_function as lgssm_h
from tests._test_utils import get_system


@pytest.fixture(scope="session")
def config():
    jax.config.update("jax_enable_x64", True)


@pytest.mark.parametrize("dim_x", [1, 2, 3])
@pytest.mark.parametrize("seed", [0, 42])
def test_predict_standard_vs_sqrt(dim_x, seed):
    np.random.seed(seed)
    x, chol_x, F, Q, cholQ, b, _ = get_system(dim_x, dim_x)

    chol_x = _sqrt_predict(F, cholQ, b, chol_x)
    x = _standard_predict(F, Q, b, x)

    np.testing.assert_allclose(x.mean, chol_x.mean, atol=1e-5)
    np.testing.assert_allclose(x.cov, chol_x.chol @ chol_x.chol.T, atol=1e-5)


@pytest.mark.parametrize("dim_x", [1, 3])
@pytest.mark.parametrize("dim_y", [1, 2, 3])
@pytest.mark.parametrize("seed", [0, 42])
def test_update_standard_vs_sqrt(dim_x, dim_y, seed):
    np.random.seed(seed)
    x, chol_x, H, R, cholR, c, y = get_system(dim_x, dim_y)

    x = _standard_update(H, R, c, x, y)
    chol_x = _sqrt_update(H, cholR, c, chol_x, y)

    np.testing.assert_allclose(x.cov, chol_x.chol @ chol_x.chol.T, atol=1e-5)
    np.testing.assert_allclose(x.mean, chol_x.mean, atol=1e-5)


@pytest.mark.parametrize("dim_x", [1, 3])
@pytest.mark.parametrize("dim_y", [1, 2, 3])
@pytest.mark.parametrize("seed", [0, 42])
@pytest.mark.parametrize("sqrt", [True, False])
@pytest.mark.parametrize("linearization_method", [extended, cubature])
def test_filter_no_noise(dim_x, dim_y, seed, sqrt, linearization_method):
    np.random.seed(seed)
    x0, chol_x0, F, Q, cholQ, b, _ = get_system(dim_x, dim_x)
    x0 = MVNParams(x0.mean, x0.cov, chol_x0.chol)
    _, _, H, R, cholR, c, _ = get_system(dim_x, dim_y)
    true_states, observations = get_data(x0.mean, F, H, R, Q, b, c, 100)
    transition_model = FunctionalModel(partial(lgssm_f, A=F), MVNParams(b, Q, cholQ))
    observation_model = FunctionalModel(partial(lgssm_h, H=H), MVNParams(c, 0 * R, 0 * cholR))

    filtered_states = filtering(observations, x0, transition_model, observation_model, linearization_method, sqrt, None)

    np.testing.assert_allclose(filtered_states.mean, true_states)
