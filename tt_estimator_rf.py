#!/usr/bin/env python3
"""This is the random forest regressor model portion of the tagtracker estimator.

Copyright (C) 2023 Julias Hocking

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
    POSSIBLE = True
except ModuleNotFoundError:
    POSSIBLE = False

# Constants for model states
INCOMPLETE = "incomplete"  # initialized but not ready to use
READY = "ready"  # model is ready to use
OK = "ok"  # model has been used to create a guess OK
ERROR = "error"  # the model is unusable, in an error state

class RandomForestRegressorModel:
    """Random Forest Regressor model for bike estimation."""

    def __init__(self):
        self.befores = []
        self.afters = []
        self.rf_model = None
        self.X_train = None
        self.y_train = None
        self.nmae = None
        self.nrmse = None

        self.further_bikes = None
        self.error = ""
        self.state = INCOMPLETE



    def calculate_normalized_errors(self, bikes_so_far):
        if self.state != OK:
            return

        try:
            predicted_afters = self.rf_model.predict(np.array([bikes_so_far]).reshape(-1, 1))
            predicted_afters = int(np.mean(predicted_afters))
            actual_afters = bikes_so_far + predicted_afters

            # Calculate NMAE
            mae = abs(actual_afters - self.afters[-1])
            range_afters = max(self.afters) - min(self.afters)
            self.nmae = mae / range_afters

            # Calculate NRMSE
            mse = (actual_afters - self.afters[-1]) ** 2
            self.nrmse = np.sqrt(mse) / range_afters

            # Ensure NMAE and NRMSE are in the range [0, 1]
            self.nmae = min(1.0, max(0.0, self.nmae))
            self.nrmse = min(1.0, max(0.0, self.nrmse))
        except Exception as e:
            self.state = ERROR
            self.error = str(e)


        try:
            predicted_afters = self.rf_model.predict(np.array([bikes_so_far]).reshape(-1, 1))
            predicted_afters = int(np.mean(predicted_afters))
            actual_afters = bikes_so_far + predicted_afters
            max_actual_afters = max(self.afters)
            min_actual_afters = min(self.afters)

            # Calculate NMAE
            mae = abs(actual_afters - self.afters[-1])
            self.nmae = mae / (max_actual_afters - min_actual_afters)

            # Calculate NRMSE
            mse = (actual_afters - self.afters[-1]) ** 2
            self.nrmse = np.sqrt(mse) / (max_actual_afters - min_actual_afters)

            # Ensure NMAE and NRMSE are in the range [0, 1]
            self.nmae = min(1.0, max(0.0, self.nmae))
            self.nrmse = min(1.0, max(0.0, self.nrmse))
        except Exception as e:
            self.state = ERROR
            self.error = str(e)

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

    def guess(self, bikes_so_far):
        if self.state == ERROR:
            return
        if self.state not in [READY, OK]:
            self.state = ERROR
            self.error = "model not in ready state."
            return

        try:
            predicted_afters = self.rf_model.predict(np.array([bikes_so_far]).reshape(-1, 1))
            self.further_bikes = int(np.mean(predicted_afters))
            self.state = OK
        except Exception as e:
            self.state = ERROR
            self.error = str(e)

        self.calculate_normalized_errors(bikes_so_far)

    def result_msg(self):
        lines = ["Using a Random Forest Regressor model:"]
        if self.state != OK:
            lines.append(f"    Can't estimate because: {self.error}")
            return lines

        lines.append(f"    Expect {self.further_bikes} more bikes.")
        lines.append(f"    Based on {len(self.befores)} data points (NMAE: {self.nmae:.2f}, NRMSE: {self.nrmse:.2f} [lower is better])")
        lines.append( "    warning: nmae and mrse are not calculating correctly right now")

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
