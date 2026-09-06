#!/bin/bash
# start_all_tmux_fixed.sh
# Version corrigée : délais augmentés, use_sim_time partout, bridge odom ajouté.

SESSION="robot_stack"
LOG_DIR="$HOME/robot_logs/$(date +%Y-%m-%d_%H-%M-%S)"
mkdir -p "$LOG_DIR"

echo "[INFO] Logs dans : $LOG_DIR"

# ============================================================
# ÉTAPE 0 — Nettoyage agressif
# ============================================================
echo "[CLEAN] Arrêt des processus résiduels..."
pkill -9 -f "gz sim"
pkill -9 -f parameter_bridge
pkill -9 -f slam_toolbox
pkill -9 -f bringup_launch
pkill -9 -f component_container
pkill -9 -f static_transform_publisher
pkill -9 -f rviz2
pkill -9 -f teleop_twist_keyboard
pkill -9 -f odom_tf_relay
rm -rf /dev/shm/fastrtps_port*
rm -rf /tmp/fastrtps*
sleep 2

ZOMBIES=$(ps aux | grep -E "gz sim|parameter_bridge|component_container" | grep -v grep | wc -l)
if [ "$ZOMBIES" -gt 0 ]; then
    echo "[WARN] $ZOMBIES processus résiduels encore détectés."
else
    echo "[OK]  Système propre."
fi

tmux kill-session -t $SESSION 2>/dev/null

# ============================================================
# FENÊTRE 0 : SIMULATION (Gazebo + Bridges + Static TF)
# ============================================================
tmux new-session -d -s $SESSION -n sim

# Pane 0.0 — Gazebo
tmux send-keys -t $SESSION:0.0 \
    'gz sim "/home/bayzo/.gz/fuel/fuel.gazebosim.org/openrobotics/worlds/tugbot in warehouse/2/tugbot_warehouse.sdf" 2>&1 | tee '"$LOG_DIR"'/01_gazebo.log' C-m

# Pane 0.1 — Les 5 bridges + static_transform (avec use_sim_time)
tmux split-window -v -t $SESSION:0
tmux send-keys -t $SESSION:0.1 '
sleep 4
source /opt/ros/jazzy/setup.bash

# Bridge clock
ros2 run ros_gz_bridge parameter_bridge /clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock 2>&1 | tee '"$LOG_DIR"'/02_clock.log &

# Bridge cmd_vel
ros2 run ros_gz_bridge parameter_bridge /model/tugbot/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist \
  --ros-args -r /model/tugbot/cmd_vel:=/cmd_vel 2>&1 | tee '"$LOG_DIR"'/03_cmdvel.log &

# Bridge tf
ros2 run ros_gz_bridge parameter_bridge /model/tugbot/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V \
  --ros-args -r /model/tugbot/tf:=/tf 2>&1 | tee '"$LOG_DIR"'/04_tf.log &

# Bridge scan
ros2 run ros_gz_bridge parameter_bridge \
  /world/world_demo/model/tugbot/link/scan_front/sensor/scan_front/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan \
  --ros-args -r /world/world_demo/model/tugbot/link/scan_front/sensor/scan_front/scan:=/scan 2>&1 | tee '"$LOG_DIR"'/05_scan.log &

# Bridge odométrie (NOUVEAU — essentiel pour que /odom existe)
ros2 run ros_gz_bridge parameter_bridge /model/tugbot/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry \
  --ros-args -r /model/tugbot/odometry:=/odom 2>&1 | tee '"$LOG_DIR"'/06_odom.log &

# Static transform base_link → LiDAR (avec use_sim_time)
ros2 run tf2_ros static_transform_publisher 0.221 0 0.140 0 0 0 base_link tugbot/scan_front/scan_front \
  --ros-args -p use_sim_time:=true 2>&1 | tee '"$LOG_DIR"'/07_static_tf.log &

wait' C-m

# ============================================================
# FENÊTRE 1 : NAV2 (délai augmenté à 25s)
# ============================================================
tmux new-window -t $SESSION -n nav2
tmux send-keys -t $SESSION:1 '
sleep 25
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch nav2_bringup bringup_launch.py use_sim_time:=true \
  slam:=True \
  slam_params_file:=/home/bayzo/slam_config/mapper_params_online_async.yaml \
  params_file:=/home/bayzo/nav2_config/nav2_params.yaml 2>&1 | tee '"$LOG_DIR"'/08_nav2.log' C-m
# FENÊTRE 2 : RVIZ2 (avec use_sim_time)
# ============================================================
tmux new-window -t $SESSION -n rviz
tmux send-keys -t $SESSION:2 '
sleep 28
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
rviz2 --ros-args -p use_sim_time:=true 2>&1 | tee '"$LOG_DIR"'/09_rviz.log' C-m

# ============================================================
# FENÊTRE 3 : POSE INITIALE (retardée à 35s, quand tout est stable)
# ============================================================
tmux new-window -t $SESSION -n init_pose
tmux send-keys -t $SESSION:3 '
sleep 35
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 topic pub --once /initialpose geometry_msgs/PoseWithCovarianceStamped "{
  header: {frame_id: map, stamp: {sec: 0, nanosec: 0}},
  pose: {
    pose: {position: {x: 0.0, y: 0.0, z: 0.0}, orientation: {x: 0.0, y: 0.0, z: 0.0, w: 1.0}},
    covariance: [0.25, 0, 0, 0, 0, 0, 0, 0.25, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.06853891945200942]
  }
}" 2>&1 | tee '"$LOG_DIR"'/10_init_pose.log' C-m

# ============================================================
# FENÊTRE 4 : KELLY MONITOR
# ============================================================
tmux new-window -t $SESSION -n kelly
tmux send-keys -t $SESSION:4 '
sleep 40
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 launch kelly_nav kelly_monitor_launch.py apply_to_nav2:=true d_safe:=3.0 ttc_safe:=6.0 kelly_b:=0.6 2>&1 | tee '"$LOG_DIR"'/11_kelly.log' C-m

# ============================================================
# FENÊTRE 5 : MONITORING
# ============================================================
tmux new-window -t $SESSION -n monitor
tmux send-keys -t $SESSION:5 '
sleep 42
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
ros2 topic echo /kelly/fraction 2>&1 | tee '"$LOG_DIR"'/12_monitor.log' C-m

# ============================================================
# FENÊTRE 6 : DIAGNOSTIC (pour toi)
# ============================================================
tmux new-window -t $SESSION -n diag
tmux send-keys -t $SESSION:6 '
sleep 30
echo "===== DIAGNOSTIC ====="
echo "Topics odom :"
ros2 topic list | grep odom
echo ""
echo "Frames TF (attendre 5s) :"
ros2 run tf2_tools view_frames 2>/dev/null && cat frames.pdf 2>/dev/null || echo "tf2_tools non installé, utiliser : ros2 topic echo /tf"
echo ""
echo "Statut lifecycle Nav2 :"
for node in map_server amcl planner_server controller_server bt_navigator behavior_server smoother_server velocity_smoother; do
  echo -n "$node: "
  ros2 lifecycle get /$node 2>/dev/null || echo "non trouvé"
done' C-m

# ============================================================
# FENÊTRE 7 : LIBRE
# ============================================================
tmux new-window -t $SESSION -n cmd
tmux send-keys -t $SESSION:7 '
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
echo "Logs dans : '"$LOG_DIR"'"
echo ""
echo "Commandes utiles :"
echo "  grep -iE \"error|warn|fatal\" '"$LOG_DIR"'/*.log"
echo "  tail -f '"$LOG_DIR"'/08_nav2.log"
echo "  ros2 topic list | grep odom"
echo "  ros2 topic echo /tf | grep frame_id"' C-m

tmux select-window -t $SESSION:0
tmux attach -t $SESSION
