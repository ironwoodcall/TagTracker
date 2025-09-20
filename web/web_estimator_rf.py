#!/usr/bin/env python3
"""This is the random forest regressor model portion of the tagtracker estimator.

Copyright (C) 2023-2025 Julias Hocking & Todd Glover

    Notwithstanding the licensing information below, this code may not
    be used in a commercial (for-profit, non-profit or government) setting
    without the copyright-holder's written consent.

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as published
    by the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""

# numpy and sklearn might not be present. POSSIBLE is used to indicate
# whether the Random Forest Regression model is at all possible.
try:
    import numpy as np
    from sklearn.ensemble import RandomForestRegressor
    # from sklearn.metrics import mean_squared_error
    # from sklearn.metrics import mean_absolute_error

    POSSIBLE = True
except (ModuleNotFoundError,ImportError):
    POSSIBLE = False

import common.tt_util as ut

# Constants for model states
INCOMPLETE = "incomplete"  # initialized but not ready to use
READY = "ready"  # model is ready to use
OK = "ok"  # model has been used to create a guess OK
ERROR = "error"  # the model is unusable, in an error state


def _format_measure(m):
    """Format a regression measure as a string."""
    if m is None or m != m or not isinstance(m, (float, int)):
        return "?"
    return f"{m:.2f}"


class RandomForestRegressorModel:
    """Random Forest Regressor model for bike estimation."""

    def __init__(self):
        self.befores = []
        self.afters = []
        self.rf_model = None
        self.X_train = None
        self.y_train = None
        # self.nmae = None
        # self.nrmse = None

        self.further_bikes = None
        self.error = ""
        self.state = INCOMPLETE

    # def calculate_normalized_errors(self):
    #     # Predict using the random forest model
    #     predicted_afters = self.rf_model.predict(
    #         np.array(self.befores).reshape(-1, 1)
    #     )

        # Calculate MAE and RMSE
        # mae = mean_absolute_error(self.afters, predicted_afters)
        # rmse = np.sqrt(mean_squared_error(self.afters, predicted_afters))

        # Calculate the range of the actual values
        # range_actual = max(self.afters) - min(self.afters)

        # Calculate NMAE and NRMSE
        # self.nmae = mae / range_actual
        # self.nrmse = rmse / range_actual

    def create_model(self, dates, befores, afters):
        if not POSSIBLE:
            self.state = ERROR
            self.error = "missing modules"
        if self.state == ERROR:
            return
        self.befores = befores
        self.afters = afters
        self.X_train = np.array(befores).reshape(-1, 1)
        self.y_train = np.array(afters)
        self.rf_model = RandomForestRegressor(n_estimators=100, random_state=0)
        self.rf_model.fit(self.X_train, self.y_train)
        self.state = READY

        # self.calculate_normalized_errors()

    def guess(self, bikes_so_far):
        if self.state == ERROR:
            return
        if self.state not in [READY, OK]:
            self.state = ERROR
            self.error = "model not in ready state."
            return

        try:
            predicted_afters = self.rf_model.predict(
                np.array([bikes_so_far]).reshape(-1, 1)
            )
            self.further_bikes = int(np.mean(predicted_afters))
            self.state = OK
        except Exception as e:
            self.state = ERROR
            self.error = str(e)

    def result_msg(self):
        lines = ["Using a random forest regressor model:"]
        if self.state != OK:
            lines.append(f"    Can't estimate because: {self.error}")
            return lines

        lines.append(
            f"    Expect {self.further_bikes} more {ut.plural(self.further_bikes,'bike')}."
        )
        lines.append(f"    Based on {len(self.befores)} "
                     f"data {ut.plural(len(self.befores),'point')}")
        # nmae_str = _format_measure(self.nmae)
        # nrmse_str = _format_measure(self.nrmse)
        # if nmae_str == "?" and nrmse_str == "?":
        #     lines.append("    Model quality can not be calculated.")
        # else:
        #     lines.append(
        #         f"    NMAE {nmae_str}; "
        #         f"NRMSE {nrmse_str} [lower is better]."
        #     )

        return lines


if __name__ == "__main__":
    # Example usage of the RandomForestRegressorModel class
    dates = ["2023-04-07", "2023-10-01", "2023-05-01"]
    befores = [4, 16, 18]
    afters = [250, 300, 280]

    bikes_so_far = 10  # Replace with the actual number of bikes so far
    rf_model = RandomForestRegressorModel()
    rf_model.create_model(dates, befores, afters)
    rf_model.guess(bikes_so_far)

    for line in rf_model.result_msg():
        print(line)
