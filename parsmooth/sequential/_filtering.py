from typing import Callable, Optional

import jax
import jax.numpy as jnp
from jax.scipy.linalg import solve, solve_triangular

from parsmooth._base import MVNStandard, FunctionalModel, MVNSqrt, are_inputs_compatible
from parsmooth._utils import tria, none_or_shift, none_or_concat


def filtering(observations: jnp.ndarray,
              x0: MVNStandard or MVNSqrt,
              transition_model: FunctionalModel,
              observation_model: FunctionalModel,
              linearization_method: Callable,
              nominal_trajectory: Optional[MVNStandard or MVNSqrt] = None):
    if nominal_trajectory is not None:
        are_inputs_compatible(x0, nominal_trajectory)

    def predict(F_x, cov_or_chol, b, x):
        if isinstance(x, MVNSqrt):
            return _sqrt_predict(F_x, cov_or_chol, b, x)
        return _standard_predict(F_x, cov_or_chol, b, x)

    def update(H_x, cov_or_chol, c, x, y):
        if isinstance(x, MVNSqrt):
            return _sqrt_update(H_x, cov_or_chol, c, x, y)
        return _standard_update(H_x, cov_or_chol, c, x, y)

    def body(x, inp):
        y, predict_ref, update_ref = inp

        if predict_ref is None:
            predict_ref = x
        F_x, cov_or_chol_Q, b = linearization_method(transition_model, predict_ref)
        x = predict(F_x, cov_or_chol_Q, b, x)

        if update_ref is None:
            update_ref = x
        H_x, cov_or_chol_R, c = linearization_method(observation_model, update_ref)
        x = update(H_x, cov_or_chol_R, c, x, y)
        return x, x

    predict_traj = none_or_shift(nominal_trajectory, -1)
    update_traj = none_or_shift(nominal_trajectory, 1)

    _, xs = jax.lax.scan(body, x0, (observations, predict_traj, update_traj))
    xs = none_or_concat(xs, x0, 1)
    return xs


def _standard_predict(F, Q, b, x):
    m, P = x

    m = F @ m + b
    P = Q + F @ P @ F.T

    return MVNStandard(m, P)


def _standard_update(H, R, c, x, y):
    m, P = x

    y_hat = H @ m + c
    y_diff = y - y_hat
    S = R + H @ P @ H.T

    G = P @ solve(S, H, sym_pos=True).T

    m = m + G @ y_diff
    P = P - G @ S @ G.T
    return MVNStandard(m, P)


def _sqrt_predict(F, cholQ, b, x):
    m, cholP = x

    m = F @ m + b
    cholP = tria(jnp.concatenate([F @ cholP, cholQ], axis=1))

    return MVNSqrt(m, cholP)


def _sqrt_update(H, cholR, c, x, y):
    m, cholP = x
    nx = m.shape[0]
    ny = y.shape[0]

    y_hat = H @ m + c
    y_diff = y - y_hat

    M = jnp.block([[H @ cholP, cholR],
                   [cholP, jnp.zeros_like(cholP, shape=(nx, ny))]])
    S = tria(M)

    cholP = S[ny:, ny:]

    G = S[ny:, :ny]
    I = S[:ny, :ny]

    m = m + G @ solve_triangular(I, y_diff, lower=True)

    return MVNSqrt(m, cholP)