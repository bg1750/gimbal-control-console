# Simulated device backend for the Pan-Tilt Gimbal Control Console.
#
# There is no hardware attached. This module fakes a two-axis stabilized
# camera platform so the console can be demonstrated end to end: it generates
# live attitude telemetry, responds to pan/tilt/zoom commands, and models
# connect / disconnect / homing / E-stop behavior. Everything the GUI reads
# comes from here.

import math
import random
import time


class GimbalSimulator:
    """
    Software model of a two-axis stabilized camera gimbal.

    The GUI polls `step()` on a timer and reads the public attributes below.
    Units: degrees for all angles, 0-100 for the zoom stage, 0-5 for the
    slew-rate "gear".
    """

    # Subsystems the console reports a connection status for.
    SUBSYSTEMS = ("controller", "input_device", "drive_power", "pan_motor", "tilt_motor")

    MAX_SPEED_MODE = 5
    MIN_TILT = 0.0
    MAX_TILT = 90.0

    def __init__(self):
        # Connection flags per subsystem. Start disconnected; the console can
        # bring them online (the demo auto-connects on launch).
        self.connected = {name: False for name in self.SUBSYSTEMS}

        # Live platform attitude (the disturbance the gimbal rides on).
        self.pitch = 0.0
        self.roll = 0.0
        self._pitch_target = 0.0
        self._roll_target = 0.0
        self._next_disturbance = 0.0

        # Pan axis (continuous heading, 0-360).
        self.heading = 0.0
        self._pan_rate = 0.0            # deg/sec, signed; set by nudging pan

        # Tilt axis (commanded elevation of the camera).
        self.tilt_angle = 0.0
        self._tilt_target = 0.0
        self.tilt_moving = False

        # Zoom / focus stage (0 = retracted, 100 = fully extended).
        self.zoom_position = 0.0
        self._zoom_target = 0.0
        self.zoom_extended = False
        self.zoom_moving = False

        # Slew-rate gear, 0 (hold) .. MAX_SPEED_MODE (fast).
        self.speed_mode = 0

        # Safety.
        self.estopped = False

        self._last_step = time.monotonic()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------
    def connect(self, subsystem):
        if subsystem in self.connected:
            self.connected[subsystem] = True

    def connect_all(self):
        for name in self.SUBSYSTEMS:
            self.connected[name] = True

    def disconnect(self, subsystem):
        if subsystem in self.connected:
            self.connected[subsystem] = False

    def is_connected(self, subsystem):
        return self.connected.get(subsystem, False)

    @property
    def fully_online(self):
        return all(self.connected.values())

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def set_speed_mode(self, mode):
        self.speed_mode = max(0, min(self.MAX_SPEED_MODE, int(mode)))

    def gear_up(self):
        self.set_speed_mode(self.speed_mode + 1)

    def gear_down(self):
        self.set_speed_mode(self.speed_mode - 1)

    def nudge_pan(self, direction):
        """direction: -1 (CCW) or +1 (CW). Pan speed scales with the gear."""
        if self.estopped or not self.is_connected("pan_motor"):
            return
        self._pan_rate = direction * (8.0 + 12.0 * self.speed_mode)

    def stop_pan(self):
        self._pan_rate = 0.0

    def set_tilt_angle(self, angle):
        if self.estopped or not self.is_connected("tilt_motor"):
            return False
        angle = max(self.MIN_TILT, min(self.MAX_TILT, float(angle)))
        self._tilt_target = angle
        self.tilt_moving = True
        return True

    def home_tilt(self):
        return self.set_tilt_angle(0.0)

    def toggle_zoom(self):
        if self.estopped or not self.is_connected("tilt_motor"):
            return False
        self._zoom_target = 0.0 if self.zoom_extended else 100.0
        self.zoom_extended = not self.zoom_extended
        self.zoom_moving = True
        return True

    def home_zoom(self):
        if self.estopped:
            return False
        self._zoom_target = 0.0
        self.zoom_extended = False
        self.zoom_moving = True
        return True

    def engage_estop(self):
        """Latch the emergency stop: freeze all motion."""
        self.estopped = True
        self._pan_rate = 0.0
        self._tilt_target = self.tilt_angle
        self._zoom_target = self.zoom_position
        self.tilt_moving = False
        self.zoom_moving = False
        self.speed_mode = 0

    def reset_estop(self):
        self.estopped = False

    # ------------------------------------------------------------------
    # Simulation tick
    # ------------------------------------------------------------------
    def step(self):
        """Advance the model by the real elapsed time since the last call."""
        now = time.monotonic()
        dt = min(0.1, now - self._last_step)  # clamp so a stall can't jump the sim
        self._last_step = now

        self._update_attitude(dt, now)
        self._update_pan(dt)
        self._update_tilt(dt)
        self._update_zoom(dt)

    def _update_attitude(self, dt, now):
        # The platform base drifts under simulated disturbance; the gimbal is
        # "riding" it. Re-roll a gentle target periodically and ease toward it,
        # then add a little high-frequency jitter so the horizon never freezes.
        if not self.is_connected("controller"):
            return
        if now >= self._next_disturbance:
            self._pitch_target = random.uniform(-12.0, 12.0)
            self._roll_target = random.uniform(-15.0, 15.0)
            self._next_disturbance = now + random.uniform(1.5, 3.5)
        ease = min(1.0, dt * 1.5)
        self.pitch += (self._pitch_target - self.pitch) * ease
        self.roll += (self._roll_target - self.roll) * ease
        self.pitch += math.sin(now * 2.3) * 0.15
        self.roll += math.sin(now * 3.1) * 0.2

    def _update_pan(self, dt):
        if self._pan_rate:
            self.heading = (self.heading + self._pan_rate * dt) % 360.0

    def _update_tilt(self, dt):
        if not self.tilt_moving:
            return
        rate = 25.0 + 10.0 * self.speed_mode  # deg/sec, faster in higher gears
        delta = self._tilt_target - self.tilt_angle
        step = rate * dt
        if abs(delta) <= step:
            self.tilt_angle = self._tilt_target
            self.tilt_moving = False
        else:
            self.tilt_angle += step * (1 if delta > 0 else -1)

    def _update_zoom(self, dt):
        if not self.zoom_moving:
            return
        rate = 60.0  # percent/sec
        delta = self._zoom_target - self.zoom_position
        step = rate * dt
        if abs(delta) <= step:
            self.zoom_position = self._zoom_target
            self.zoom_moving = False
        else:
            self.zoom_position += step * (1 if delta > 0 else -1)
