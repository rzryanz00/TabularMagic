import statsmodels.api as sm
import numpy as np
from ..metrics.regression_scoring import RegressionScorer
from ..data.datahandler import DataEmitter
from scipy.stats import chi2
import pandas as pd
from typing import Literal
from ..utils import ensure_arg_list_uniqueness

def score_count_model(
    X_train: pd.DataFrame,
    y_train: pd.DataFrame,
    feature_list,
    metric: Literal["aic", "bic"],
    model: Literal["poisson", "negativebinomial"]
) -> float:
    """Calculates the AIC or BIC score for a given model.

    Parameters
    ----------
    X_train : pd.DataFrame
        The training data.
    y_train : pd.Series
        The training target.
    feature_list : list[str]
        The list of features to include in the model.
    metric : str
        The metric to use for scoring. Either 'aic' or 'bic'.
    model : Literal["poisson", "negativebinomial"]
        The model that should be considered.

    Returns
    -------
    float
        The AIC or BIC score for the model.
    """
    if len(feature_list) == 0:
        return np.inf

    subset_X_train = X_train[feature_list]
    if model == "poisson":
        new_model = sm.GLM(y_train, subset_X_train, family=sm.families.Poisson()).fit(
        cov_type="HC3"
    )
    else:
        new_model = sm.NegativeBinomial(y_train, X_train).fit(cov_type="HC3")

    if metric == "aic":
        score = new_model.aic
    elif metric == "bic":
        score = new_model.bic
    return score


class CountLinearModel:
    """Statsmodels GLM wrapper that automatically chooses a Poisson or
    Negative Binomial GLM based on a likelihood ratio test for overdispersion
    """

    def __init__(self, name: str | None = None):
        """
        Initializes a CountLinearModel object. Regresses y on X.

        Parameters
        ----------
        name : str.
            Default: None. Determines how the model shows up in the reports.
            If None, the name is set to be the class name.
        """
        self.estimator = None
        self._name = name
        self._type = None
        if self._name is None:
            self._name = "Count GLM"

    def specify_data(self, dataemitter: DataEmitter):
        """Adds a DataEmitter object to the model.

        Parameters
        ----------
        dataemitter : DataEmitter 
            The DataEmitter containing all the data.
        """
        self._dataemitter = dataemitter

    def fit(self):
        """Fits the model based on the data specified."""
        y_scaler = self._dataemitter.y_scaler()

        # Emit the training data
        X_train, y_train = self._dataemitter.emit_train_Xy()
        # Add a constant to the Design Matrix
        X_train = sm.add_constant(X_train)

        # Fit Poisson and ngative binomial glm and perform likelihood ratio test
        poisson_estimator = sm.GLM(y_train, X_train, family=sm.families.Poisson()).fit(
            cov_type="HC3"
        )

        negbin_estimator = sm.NegativeBinomial(y_train, X_train).fit(cov_type="HC3")

        # Extract log-likelihoods
        poisson_llf = poisson_estimator.llf
        negbin_llf = negbin_estimator.llf

        # Based off of odTest from pscl package in r
        d = 2 * (negbin_llf - poisson_llf)
        pval = (1 - chi2.cdf(d, df=1)) / 2
        alpha = 0.05

        # test
        print(f"pval: {pval}")

        # H0: Poisson; Ha: Negative Binomial
        if pval <= alpha:
            self.estimator = negbin_estimator
            self._type = "negativebinomial"
        else:
            self.estimator = poisson_estimator
            self._type = "poisson"

        # Get the predictions from the training dataset
        y_pred_train: np.ndarray = self.estimator.predict(exog=X_train).to_numpy()
        if y_scaler is not None:
            y_pred_train = y_scaler.inverse_transform(y_pred_train)
            y_train = y_scaler.inverse_transform(y_train)

        # Emit the test data
        X_test, y_test = self._dataemitter.emit_test_Xy()
        X_test = sm.add_constant(X_test)

        n_predictors = X_train.shape[1]

        self.train_scorer = RegressionScorer(
            y_pred=y_pred_train,
            y_true=y_train.to_numpy(),
            n_predictors=n_predictors,
            name=self._name,
        )

        y_pred_test = self.estimator.predict(X_test).to_numpy()
        if y_scaler is not None:
            y_pred_test = y_scaler.inverse_transform(y_pred_test)
            y_test = y_scaler.inverse_transform(y_test)

        self.test_scorer = RegressionScorer(
            y_pred=y_pred_test,
            y_true=y_test.to_numpy(),
            n_predictors=n_predictors,
            name=self._name,
        )


    @ensure_arg_list_uniqueness()
    def step(
        self,
        direction: Literal["both", "backward", "forward"] = "backward",
        criteria: Literal["aic", "bic"] = "aic",
        kept_vars: list[str] | None = None,
        all_vars: list[str] | None = None,
        start_vars: list[str] | None = None,
        max_steps: int = 100,
    ) -> list[str]:
        """This method implements stepwise selection for identifying important
        features. If the direction is set to forward, the algorithm will start
        with no selected variables and will at each time step add every 
        left-out feature to the model separately. the left-out feature
        that results in the best improvement in the metric (aic or bic) will
        be selected as an important feature. This happens until all variables
        are added or adding a left-out variable does not improve the metric
        of choice.
        
        If the direction is set to backward, the algorithm will start with all
        variables selected and will at each time step remove each included
        variable separately. The variable that results in the best improvement
        in the metric when removed from the model will be removed from the 
        list of selected features.

        Categorical variables will either be included or excluded as a whole.

        Parameters
        ----------
        direction : Literal["both", "backward", "forward"]
            Default: 'backward'. The direction of the stepwise selection.

        criteria : Literal["aic", "bic"]
            Default: 'aic'. The criteria to use for selecting the best model.

        kept_vars : list[str]
            Default: None. The variables that should be kept in the model.
            If None, defaults to empty list.

        all_vars : list[str]
            Default: None. The variables that are candidates for inclusion in the model.
            If None, defaults to all variables in the training data.

        start_vars : list[str]
            Default: None. The variables to start the bidirectional stepwise selection with.
            Ignored if direction is not 'both'. If direction is 'both' and
            start_vars is None, then the starting variables are the kept_vars.

        max_steps : int
            Default: 100. The maximum number of steps to take.

        Returns
        -------
        list[str]
            The subset of predictors that are most likely to be significant.
        """
        # This check is unique for count regression
        if self.estimator == None:
            raise ValueError("Must fit model first")

        if max_steps <= 0:
            raise ValueError("max_steps cannot be non-positive")

        X_train, y_train = self._dataemitter.emit_train_Xy()

        # set upper to all possible variables if nothing is specified
        if all_vars is None:
            all_vars = X_train.columns.tolist()
        if kept_vars is None:
            kept_vars = []

        # ensure that kept vars are in all vars
        for var in kept_vars:
            if var not in all_vars:
                raise ValueError(f"{var} is not in all_vars")

        # set our current variables to our starting list
        if direction == "forward":
            included_vars = kept_vars.copy()
        elif direction == "backward":
            included_vars = all_vars.copy()
        elif direction == "both":
            if start_vars is None:
                included_vars = kept_vars.copy()
            else:
                included_vars = start_vars.copy()

        # set our starting score and best models
        current_score = score_count_model(
            X_train,
            y_train,
            included_vars,
            metric=criteria,
            model=self._type
        )
        current_step = 0

        while current_step < max_steps:
            # Forward step
            if direction == "forward":
                excluded = list(set(all_vars) - set(included_vars))

                best_score = current_score
                var_to_add = None
                for new_var in excluded:
                    candidate_features = included_vars + [new_var]
                    score = score_count_model(
                        X_train,
                        y_train,
                        candidate_features,
                        metric=criteria,
                        model=self._type
                    )
                    if score < best_score:
                        best_score = score
                        var_to_add = new_var

                # If we didn't find a variable to add (score is not better), break
                if var_to_add is None:
                    break

                included_vars.append(var_to_add)

            # Backward step
            elif direction == "backward":
                if len(included_vars) <= len(kept_vars):
                    break

                best_score = current_score
                var_to_remove = None

                for candidate in included_vars:
                    if candidate in kept_vars:
                        continue

                    candidate_features = included_vars.copy()
                    candidate_features.remove(candidate)
                    score = score_ols_model(
                        X_train,
                        y_train,
                        candidate_features,
                        metric=criteria,
                    )
                    if score < best_score:
                        best_score = score
                        var_to_remove = candidate

                if var_to_remove is None:
                    break

                included_vars.remove(var_to_remove)

            elif direction == "both":
                excluded = list(set(all_vars) - set(included_vars))

                best_score = current_score

                best_forward_score = current_score
                var_to_add = None
                for new_var in excluded:
                    candidate_features = included_vars + [new_var]
                    score = score_ols_model(
                        X_train,
                        y_train,
                        candidate_features,
                        metric=criteria,
                    )
                    if score < best_forward_score:
                        best_forward_score = score
                        var_to_add = new_var

                best_backward_score = current_score
                var_to_remove = None

                for candidate in included_vars:
                    if candidate in kept_vars:
                        continue

                    candidate_features = included_vars.copy()
                    candidate_features.remove(candidate)
                    score = score_ols_model(
                        X_train,
                        y_train,
                        candidate_features,
                        metric=criteria,
                    )
                    if score < best_backward_score:
                        best_backward_score = score
                        var_to_remove = candidate

                if best_forward_score < best_backward_score:
                    if var_to_add is None:
                        break
                    included_vars.append(var_to_add)
                    best_score = best_forward_score
                else:
                    if var_to_remove is None:
                        break
                    included_vars.remove(var_to_remove)
                    best_score = best_backward_score

            current_score = best_score
            current_step += 1

        return included_vars


    def __str__(self):
        return self._name
