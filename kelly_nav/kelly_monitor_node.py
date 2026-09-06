#!/usr/bin/env python3
"""
kelly_monitor_node.py

Estime en continu le risque de collision a partir du LiDAR et de l'odometrie,
calcule une fraction de Kelly f* (adaptee de la formule de dimensionnement de
mise de John Kelly, 1956) et l'utilise pour moduler dynamiquement :
  - la vitesse max envoyee au controller_server de Nav2 (MPPI)
  - le rayon d'inflation (distance de securite) du costmap local

Formule de Kelly classique :   f* = p - (1 - p) / b
    p = probabilite estimee de "trajectoire sure" (analogue a la proba de
        gagner le pari)
    b = "cote" = gain relatif espere (aller plus vite) / cout relatif d'une
        collision. Parametre reglable (kelly_b).
    f* = fraction du capital a miser -> ici, fraction de la vitesse max
         nominale que le robot est autorise a utiliser.

p est lui-meme estime a partir de deux indicateurs de risque issus du LiDAR
et de la vitesse courante :
  - distance minimale aux obstacles dans un cone avant (min_distance)
  - temps avant collision estime (TTC = min_distance / v)

p = min(p_distance, p_ttc), chacun interpole lineairement entre un seuil
"critique" (p=0) et un seuil "sur" (p=1).
"""

import math

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rcl_interfaces.srv import SetParameters
from rcl_interfaces.msg import Parameter as ParameterMsg, ParameterValue, ParameterType

from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry
from std_msgs.msg import Float32


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


class KellyMonitorNode(Node):
    def __init__(self):
        super().__init__('kelly_monitor_node')

        # ---------------- Parametres reglables ----------------
        self.declare_parameter('front_angle_deg', 120.0)      # largeur du cone avant analyse
        self.declare_parameter('d_critical', 0.35)             # m, distance = danger total (p=0)
        self.declare_parameter('d_safe', 1.5)                  # m, distance = zone sure (p=1)
        self.declare_parameter('ttc_critical', 1.0)             # s, TTC = danger total (p=0)
        self.declare_parameter('ttc_safe', 4.0)                 # s, TTC = zone sure (p=1)
        self.declare_parameter('kelly_b', 1.5)                  # cote gain/perte (>0)
        self.declare_parameter('f_min', 0.15)                   # fraction min de vitesse (ne jamais s'arreter net)
        self.declare_parameter('v_nominal_max', 0.5)            # m/s, vitesse max "pleine confiance"
        self.declare_parameter('inflation_base', 0.20)          # m, rayon d'inflation en zone sure
        self.declare_parameter('inflation_extra', 0.35)         # m, rayon d'inflation ajoute au risque max
        self.declare_parameter('publish_rate_hz', 5.0)
        self.declare_parameter('apply_to_nav2', True)           # False = calcule/publie seulement, ne touche pas Nav2
        self.declare_parameter('controller_server_name', 'controller_server')
        self.declare_parameter('controller_speed_param', 'FollowPath.vx_max')
        self.declare_parameter('costmap_node_name', 'local_costmap/local_costmap')
        self.declare_parameter('inflation_param', 'inflation_layer.inflation_radius')

        self.front_angle = math.radians(self.get_parameter('front_angle_deg').value)
        self.apply_to_nav2 = self.get_parameter('apply_to_nav2').value

        # ---------------- Etat ----------------
        self.current_speed = 0.0
        self.min_distance = float('inf')
        self.ttc = float('inf')

        # ---------------- Abonnements ----------------
        self.create_subscription(LaserScan, '/scan', self.scan_cb, 10)
        self.create_subscription(Odometry, '/odom', self.odom_cb, 10)

        # ---------------- Publications (pour rqt_plot / logging / rapport) ----------------
        self.pub_p = self.create_publisher(Float32, '/kelly/p_safe', 10)
        self.pub_f = self.create_publisher(Float32, '/kelly/fraction', 10)
        self.pub_ttc = self.create_publisher(Float32, '/kelly/ttc', 10)
        self.pub_dmin = self.create_publisher(Float32, '/kelly/min_distance', 10)
        self.pub_vmax = self.create_publisher(Float32, '/kelly/applied_vmax', 10)
        self.pub_infl = self.create_publisher(Float32, '/kelly/applied_inflation', 10)

        # ---------------- Clients de parametres Nav2 (dynamic reconfigure) ----------------
        if self.apply_to_nav2:
            ctrl_name = self.get_parameter('controller_server_name').value
            costmap_name = self.get_parameter('costmap_node_name').value
            self.ctrl_client = self.create_client(SetParameters, f'/{ctrl_name}/set_parameters')
            self.costmap_client = self.create_client(SetParameters, f'/{costmap_name}/set_parameters')

        period = 1.0 / float(self.get_parameter('publish_rate_hz').value)
        self.timer = self.create_timer(period, self.compute_and_apply)

        self.get_logger().info('kelly_monitor_node demarre (critere de Kelly adapte a la navigation)')

    # ------------------------------------------------------------------
    def scan_cb(self, msg: LaserScan):
        n = len(msg.ranges)
        if n == 0:
            return
        # indices correspondant au cone avant [-front_angle/2, +front_angle/2]
        # on suppose angle_min/angle_max couvrant potentiellement 360 deg,
        # angle 0 = avant du robot.
        half = self.front_angle / 2.0
        best = float('inf')
        for i, r in enumerate(msg.ranges):
            if not math.isfinite(r) or r <= msg.range_min or r >= msg.range_max:
                continue
            angle = msg.angle_min + i * msg.angle_increment
            # normaliser dans [-pi, pi]
            angle = math.atan2(math.sin(angle), math.cos(angle))
            if -half <= angle <= half:
                if r < best:
                    best = r
        self.min_distance = best

    def odom_cb(self, msg: Odometry):
        vx = msg.twist.twist.linear.x
        vy = msg.twist.twist.linear.y
        self.current_speed = math.hypot(vx, vy)

    # ------------------------------------------------------------------
    def compute_p_safe(self):
        d_crit = self.get_parameter('d_critical').value
        d_safe = self.get_parameter('d_safe').value
        ttc_crit = self.get_parameter('ttc_critical').value
        ttc_safe = self.get_parameter('ttc_safe').value

        d = self.min_distance
        if not math.isfinite(d):
            p_dist = 1.0
        else:
            p_dist = clamp((d - d_crit) / max(1e-6, (d_safe - d_crit)), 0.0, 1.0)

        v = self.current_speed
        if v > 1e-3 and math.isfinite(d):
            self.ttc = d / v
        else:
            self.ttc = float('inf')

        if not math.isfinite(self.ttc):
            p_ttc = 1.0
        else:
            p_ttc = clamp((self.ttc - ttc_crit) / max(1e-6, (ttc_safe - ttc_crit)), 0.0, 1.0)

        return min(p_dist, p_ttc)

    def kelly_fraction(self, p):
        b = max(1e-3, self.get_parameter('kelly_b').value)
        f_min = self.get_parameter('f_min').value
        f = p - (1.0 - p) / b
        return clamp(f, f_min, 1.0)

    # ------------------------------------------------------------------
    def compute_and_apply(self):
        p = self.compute_p_safe()
        f = self.kelly_fraction(p)

        v_nominal = self.get_parameter('v_nominal_max').value
        v_max = f * v_nominal

        infl_base = self.get_parameter('inflation_base').value
        infl_extra = self.get_parameter('inflation_extra').value
        inflation = infl_base + (1.0 - f) * infl_extra

        # publications (toujours, meme si apply_to_nav2=False -> mode "log only")
        self.pub_p.publish(Float32(data=float(p)))
        self.pub_f.publish(Float32(data=float(f)))
        self.pub_ttc.publish(Float32(data=float(self.ttc if math.isfinite(self.ttc) else 999.0)))
        self.pub_dmin.publish(Float32(data=float(self.min_distance if math.isfinite(self.min_distance) else 999.0)))
        self.pub_vmax.publish(Float32(data=float(v_max)))
        self.pub_infl.publish(Float32(data=float(inflation)))

        if self.apply_to_nav2:
            self.set_remote_param(self.ctrl_client, self.get_parameter('controller_speed_param').value, v_max)
            self.set_remote_param(self.costmap_client, self.get_parameter('inflation_param').value, inflation)

    def set_remote_param(self, client, param_name, value: float):
        if not client.service_is_ready():
            # ne bloque pas la boucle si Nav2 pas encore lance
            return
        req = SetParameters.Request()
        pmsg = ParameterMsg()
        pmsg.name = param_name
        pmsg.value = ParameterValue(type=ParameterType.PARAMETER_DOUBLE, double_value=float(value))
        req.parameters = [pmsg]
        client.call_async(req)


def main(args=None):
    rclpy.init(args=args)
    node = KellyMonitorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
