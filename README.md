# kelly_nav — Navigation adaptative au risque (critère de Kelly)

## 1. Principe

Le critère de Kelly (John L. Kelly Jr., Bell Labs, 1956) est à l'origine
une formule de dimensionnement optimal d'une mise en pari ou en
investissement, maximisant la croissance logarithmique du capital sur le
long terme :

```
f* = p/L - q/G
```

- `p` : probabilité de succès
- `q = 1 - p` : probabilité d'échec
- `L` : fraction du capital perdue en cas d'échec
- `G` : fraction du capital gagnée en cas de succès
- `f*` : fraction optimale du capital à engager

Adaptation à la navigation autonome retenue dans ce package :

| Finance | Navigation |
|---|---|
| Capital à miser | Vitesse maximale autorisée |
| Probabilité de succès `p` | Probabilité de trajectoire sûre (estimée via LiDAR) |
| Fraction perdue `L` | Sévérité potentielle d'une collision |
| Fraction gagnée `G` | Bénéfice d'une navigation rapide |
| Fraction misée `f*` | Fraction de la vitesse nominale maximale utilisée |

La probabilité `p` est estimée à partir de deux indicateurs extraits du
LiDAR et de l'odométrie :

- distance minimale aux obstacles dans un cône avant (120° par défaut) ;
- temps avant collision estimé (TTC = distance minimale / vitesse
  courante).

Chaque indicateur est interpolé linéairement entre un seuil critique
(risque maximal) et un seuil sûr (risque nul) ; la valeur de `p` retenue
est le minimum des deux.

La fraction `f*` obtenue module en temps réel, via les services
`set_parameters` de ROS 2 :

- la vitesse maximale transmise au contrôleur MPPI de Nav2 ;
- le rayon d'inflation du costmap local (distance de sécurité).

## 2. Structure du package

```
kelly_nav/
├── kelly_nav/
│   ├── __init__.py
│   └── kelly_monitor_node.py
├── launch/
│   └── kelly_monitor_launch.py
├── package.xml
├── setup.py
├── setup.cfg
└── resource/kelly_nav
```

## 3. Installation

```bash
cd ~/ros2_ws/src
# copier kelly_nav ici
cd ~/ros2_ws
colcon build --packages-select kelly_nav
source install/setup.bash
```

## 4. Paramètres

| Paramètre | Défaut | Rôle |
|---|---|---|
| `d_critical` | 0.35 m | distance = danger maximal |
| `d_safe` | 1.5 m | distance = zone sûre |
| `ttc_critical` | 1.0 s | temps avant collision = danger maximal |
| `ttc_safe` | 4.0 s | temps avant collision = zone sûre |
| `kelly_b` | 1.5 | ratio bénéfice/coût (fraction gagnée `G`) |
| `f_min` | 0.15 | fraction minimale de vitesse |
| `v_nominal_max` | 0.5 m/s | vitesse nominale de référence |
| `inflation_base` | 0.20 m | distance de sécurité en zone sûre |
| `inflation_extra` | 0.35 m | marge supplémentaire en zone à risque |
| `apply_to_nav2` | true | si false, calcule et publie sans modifier Nav2 |

## 5. Lancement

```bash
ros2 launch kelly_nav kelly_monitor_launch.py apply_to_nav2:=true
```

Mode observation seule (sans modification de Nav2) :

```bash
ros2 launch kelly_nav kelly_monitor_launch.py apply_to_nav2:=false
```

## 6. Topics publiés

| Topic | Contenu |
|---|---|
| `/kelly/p_safe` | probabilité de trajectoire sûre estimée |
| `/kelly/fraction` | fraction de Kelly calculée |
| `/kelly/ttc` | temps avant collision estimé |
| `/kelly/min_distance` | distance minimale détectée |
| `/kelly/applied_vmax` | vitesse maximale appliquée à Nav2 |
| `/kelly/applied_inflation` | rayon d'inflation appliqué au costmap |

## 7. Dépendances

- ROS 2 Jazzy
- Nav2 (`controller_server` avec plugin MPPI, costmap local avec
  `inflation_layer`)
- `rclpy`, `sensor_msgs`, `nav_msgs`, `std_msgs`, `rcl_interfaces`

## 8. Fichiers additionnels

- `scripts/start_all_tmux.sh` : script de lancement automatisé de la
  chaîne complète (Gazebo, bridges ROS 2, Nav2, RViz2, kelly_nav) via
  tmux, utilisé pour les tests et démonstrations.
- `config/nav2_params.yaml` : configuration Nav2 utilisée (costmaps,
  contrôleur MPPI, planificateur).
- `config/mapper_params_online_async.yaml` : configuration de
  `slam_toolbox` (mode localisation avec extension de carte).