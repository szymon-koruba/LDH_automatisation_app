import time


class NonLinearPID:
    def __init__(self, Kp: float = 2.0, Ki: float = 0.1, Kd: float = 0.5, power: float = 2.0):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.power = power

        self.last_error = 0.0
        self.integral = 0.0
        self.last_time = None

    def compute(self, current_ph: float, target_ph: float, max_offset: float):
        now = time.time()
        if self.last_time is None:
            dt = 1.0
        else:
            dt = now - self.last_time
            if dt <= 0:
                dt = 0.001
        self.last_time = now

        error = abs(current_ph - target_ph)
        print(error)


        if error <= 0:
            self.integral = 0.0
            self.last_error = 0.0
            return 0.0


        norm_error = error / max_offset if max_offset > 0 else error

        nl_error = (abs(norm_error) ** self.power) * (1.0 if norm_error > 0 else -1.0)

        p_term = self.Kp * nl_error

        self.integral += nl_error * dt
        i_term = self.Ki * self.integral

        d_error = (nl_error - self.last_error) / dt
        d_term = self.Kd * d_error
        self.last_error = nl_error

        raw_voltage = (p_term + i_term + d_term) * 8.0


        if raw_voltage > 8.0:
            voltage = 8.0
            self.integral -= nl_error * dt
        elif raw_voltage < 0.0:
            voltage = 0.0
            self.integral = 0.0
        else:
            voltage = raw_voltage

        return round(voltage, 1)

    def reset(self):
        self.integral = 0.0
        self.last_error = 0.0
        self.last_time = None