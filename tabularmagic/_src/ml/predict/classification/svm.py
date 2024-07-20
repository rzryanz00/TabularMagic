import numpy as np
from sklearn.svm import SVC
from typing import Mapping, Iterable, Literal
from .base import BaseC, HyperparameterSearcher
from optuna.distributions import (
    FloatDistribution,
    IntDistribution,
    CategoricalDistribution,
)
from ....feature_selection import BaseFSC


class SVMC(BaseC):
    """Support Vector Machine with kernel trick.

    Like all BaseC-derived classes, hyperparameter selection is
    performed automatically during training. The cross validation and
    hyperparameter selection process can be modified by the user.
    """

    def __init__(
        self,
        type: Literal["linear", "poly", "rbf"] = "rbf",
        hyperparam_search_method: Literal[None, "grid", "random"] = None,
        hyperparam_search_space: Mapping[str, Iterable] | None = None,
        feature_selectors: list[BaseFSC] | None = None,
        max_n_features: int | None = None,
        name: str | None = None,
        **kwargs,
    ):
        """
        Initializes a SVMC object.

        Parameters
        ----------
        type : Literal['linear', 'poly', 'rbf'].
            Default: 'rbf'. The type of kernel to use.
        hyperparam_search_method : Literal[None, 'grid', 'optuna'].
            Default: None. If None, a classification-specific default hyperparameter
            search is conducted.
        hyperparam_search_space : Mapping[str, Iterable | BaseDistribution].
            Default: None. If None, a classification-specific default hyperparameter
            search is conducted.
        feature_selectors : list[BaseFSC].
            Default: None. If not None, specifies the feature selectors for the
            VotingSelectionReport.
        max_n_features : int | None.
            Default: None. 
            Only useful if feature_selectors is not None. 
            If None, then all features with at least 50% support are selected.
        name : str.
            Default: None. Determines how the model shows up in the reports.
            If None, the name is set to be the class name.
        kwargs : Key word arguments are passed directly into the
            intialization of the HyperparameterSearcher class. In particular,
            inner_cv and inner_cv_seed can be set via kwargs.

        **kwargs
        --------------
        inner_cv : int | BaseCrossValidator.
            Default: 5.
        inner_cv_seed : int.
            Default: 42.
        n_jobs : int.
            Default: 1. Number of parallel jobs to run.
        verbose : int.
            Default: 0. scikit-learn verbosity level.
        n_trials : int.
            Default: 100. Number of trials for hyperparameter optimization. Only
            used if hyperparam_search_method is 'optuna'.
        """
        super().__init__()

        if name is None:
            self._name = f"SVMC({type})"
        else:
            self._name = name

        self._estimator = SVC(
            kernel=type, 
            max_iter=100, 
            probability=True
        )
        self._feature_selectors = feature_selectors
        self._max_n_features = max_n_features

        if (hyperparam_search_method is None) or (hyperparam_search_space is None):
            hyperparam_search_method = "optuna"

            if type == "linear":
                hyperparam_search_space = {
                    "C": FloatDistribution(1e-2, 1e2, log=True),
                }
            elif type == "poly":
                hyperparam_search_space = {
                    "C": FloatDistribution(1e-2, 1e2, log=True),
                    "degree": IntDistribution(2, 5),
                    "coef0": IntDistribution(0, 10),
                    "gamma": CategoricalDistribution(["scale", "auto"]),
                }
            elif type == "rbf":
                hyperparam_search_space = {
                    "C": FloatDistribution(1e-2, 1e2, log=True),
                    "gamma": CategoricalDistribution(["scale", "auto"]),
                }

        self._hyperparam_searcher = HyperparameterSearcher(
            estimator=self._estimator,
            method=hyperparam_search_method,
            hyperparam_grid=hyperparam_search_space,
            estimator_name=self._name,
            **kwargs,
        )