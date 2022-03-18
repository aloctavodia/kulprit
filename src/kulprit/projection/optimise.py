"""Restricted model projection optimiser module."""

import torch
import torch.nn as nn

from ..families import Family


class _DivLoss(nn.Module):
    """Custom Kullback-Leibler divergence loss module.

    This class computes some KL divergence loss for observations seen from the
    GLM given the reference model variate's family.

    Attributes:
        family (kulprit.families.Family): The reference model family object
    """

    def __init__(self, family):
        """Loss module constructor.

        We instantiate a `kulprit.Family` object based on the model variate's
        family which includes a Kullback-Leibler divergence function, and in the
        cases where the distribution has dispersion parameters, functions
        allowing for their respective projections.

        Args:
            family (kulprit.families.Family): The reference model family object
        """

        super().__init__()
        self.family = family

    def forward(self, y_ast, y_perp):
        """Forward method in learning loop.

        This method computes the Kullback-Leibler divergence between the
        reference model variate draws ``y_ast``and the restricted model's
        variate draws ``y_perp``. This is done using the two samples' respective
        sufficient sample statistics and a divergence equation found in the
        ``Family`` class.

        Args:
            mu_ast (torch.tensor): Tensor of learned reference model parameters
            mu_perp (torch.tensor): Tensor of submodel parameters to learn

        Returns:
            torch.tensor: Tensor of shape () containing sample KL divergence

        Raises:
            AssertionError if unexpected input dimensions
        """

        divs = self.family.kl_div(y_ast, y_perp)
        return divs


class _KulOpt(nn.Module):
    """Core optimisation solver class.

    This class solves the general problem of Kullback-Leibler divergence
    projection onto a submodel using a PyTorch neural network architecture
    for efficiency. The procedure might use this class to project the
    learned full parameter samples onto a submodel that uses a restricted
    dataset to define which parameters to include/exclude.

    Attributes:
        inv_link (function): The inverse link function of the GLM
        s (int): Number of MCMC posterior samples
        n (int): Number of observations in the GLM
        m (int): Number of parameters in the submodel
        lin (torch.nn module): The linear transformation module
    """

    def __init__(self, res_model):
        """SubModel class constructor method.

        Args:
            res_model (kulprit.ModelData): The projection restricted model object
        """

        super().__init__()
        # assign data shapes and GLM inverse link function
        self.s = res_model.s
        self.n = res_model.n
        self.m = res_model.m
        self.inv_link = res_model.link.linkinv
        # build linear component of GLM without intercept
        self.lin = nn.Linear(self.m, self.s, bias=False)

    def forward(self, X):
        """Forward method in learning loop.

        Args:
            X (torch.tensor): Design matrix (including intercept) of shape (n, m)

        Returns:
            y (torch.tensor): Model outputs of shape (n, s)

        Raises:
            AssertionError if unexpected input dimensions
        """

        # perform forward prediction step
        y = self.inv_link(self.lin.forward(X).T)
        return y
