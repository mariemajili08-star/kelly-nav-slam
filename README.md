# kelly_nav — Navigation adaptative au risque (critère de Kelly)

## 1. Le principe

Le **critère de Kelly** (John L. Kelly, Bell Labs, 1956) est à l'origine une formule
de dimensionnement de mise en pari/investissement, qui maximise la croissance du
capital sur le long terme :

```
f* = p - (1 - p) / b
```

- `p` = probabilité estimée de succès
- `b` = "cote" = gain relatif espéré si succès / perte relative si échec
- `f*` = fraction du capital à engager

**Adaptation à la navigation** (ce package) :

| Finance                          | Navigation                                      |
|-----------------------------------|--------------------------------------------------|
| Capital à miser                   | Vitesse maximale autorisée                        |
| Probabilité de gagner le pari `p` | Probabilité de trajectoire sûre (estimée LiDAR)   |
| Cote `b`                          | Ratio bénéfice (aller vite) / coût (collision)    |
| Fraction misée `f*`               | Fraction de la vitesse nominale max utilisée      |

`p` est calculé à partir de deux indicateurs de risque extraits du LiDAR et de
l'odométrie :

- **distance minimale** aux obstacles dans un cône avant (120° par défaut)
- **temps avant collision (TTC)** = distance / vitesse courante

Chaque indicateur est interpolé linéairement entre un seuil critique (risque
max, contribution = 0) et un seuil sûr (risque nul, contribution = 1) ; `p`
retenu est le **minimum** des deux (le facteur le plus défavorable domine).

`f*` obtenu module ensuite en temps réel, via les services `set_parameters`
de ROS 2 (reconfiguration dynamique, sans relancer Nav2) :

- la **vitesse max** envoyée au `controller_server` (plugin MPPI)
- le **rayon d'inflation** du costmap local (= distance de sécurité autour
  des obstacles) — plus le risque est élevé, plus la marge est grande

## 2. Installation

```bash
cd ~/ros2_ws/src
# copier ce dossier kelly_nav ici
cd ~/ros2_ws
colcon build --packages-select kelly_nav
source install/setup.bash
```

## 3. Vérifier les noms de paramètres Nav2 avant le premier lancement

Les noms exacts des paramètres dépendent de ta config `nav2_params.yaml`
(déjà présente dans `~/nav2_config/`). Vérifie avec :

```bash
ros2 param list /controller_server | grep -i vx_max
ros2 param list /local_costmap/local_costmap | grep -i inflation
```

Si les noms diffèrent de `FollowPath.vx_max` et
`inflation_layer.inflation_radius` (par ex. si ton plugin MPPI a un autre nom
de sous-espace), adapte-les au lancement avec les arguments `-p` (voir plus
bas) ou directement dans les `declare_parameter` du nœud.

## 4. Lancer

Après avoir démarré ta chaîne habituelle (Gazebo, SLAM ou carte + AMCL, Nav2) :

```bash
# Mode "log seulement" (recommandé pour le premier test) :
ros2 launch kelly_nav kelly_monitor_launch.py apply_to_nav2:=false

# Mode actif (modifie réellement Nav2 en direct) :
ros2 launch kelly_nav kelly_monitor_launch.py apply_to_nav2:=true
```

Surveiller en direct :

```bash
ros2 topic echo /kelly/p_safe
ros2 topic echo /kelly/fraction
ros2 topic echo /kelly/applied_vmax
```

Pour un graphe temps réel (utile pour ton rapport) :

```bash
rqt_plot /kelly/p_safe/data /kelly/fraction/data /kelly/min_distance/data
```

## 5. Protocole de comparaison SLAM classique vs SLAM + Kelly

Pour ton livrable "résultats avec plusieurs obstacles" en version Kelly :

1. Reprends **exactement** le même scénario d'entrepôt que pour la phase 1
   (mêmes obstacles, même objectif envoyé depuis RViz).
2. Lance une première fois **sans** `kelly_nav` (Nav2 classique) → enregistre
   vidéo + temps total + distance min aux obstacles pendant la mission.
3. Relance **avec** `kelly_nav` (`apply_to_nav2:=true`) → mêmes mesures.
4. Compare :
   - temps total pour atteindre l'objectif (Kelly devrait être plus lent en
     zone dense, similaire en zone dégagée)
   - distance minimale observée aux obstacles (Kelly devrait maintenir une
     marge plus grande dans les passages étroits)
   - éventuels arrêts / replanifications MPPI (à observer dans les logs
     `controller_server`)
5. Pour objectiver, exporte `/kelly/min_distance` et `/kelly/fraction` avec
   `ros2 bag record` pendant les deux runs, puis trace les courbes.

## 6. Paramètres réglables (tous surchargeables au lancement)

| Paramètre           | Défaut | Rôle                                            |
|----------------------|--------|--------------------------------------------------|
| `d_critical`         | 0.35 m | distance = danger maximal                        |
| `d_safe`             | 1.5 m  | distance = zone jugée sûre                        |
| `ttc_critical`       | 1.0 s  | temps avant collision = danger maximal            |
| `ttc_safe`           | 4.0 s  | temps avant collision = zone jugée sûre           |
| `kelly_b`            | 1.5    | cote bénéfice/coût (plus grand = plus agressif)   |
| `f_min`              | 0.15   | fraction min de vitesse (le robot ne s'arrête jamais net) |
| `v_nominal_max`      | 0.5 m/s| vitesse "pleine confiance" (reprends ta valeur MPPI actuelle) |
| `inflation_base`     | 0.20 m | distance de sécurité en zone sûre                 |
| `inflation_extra`    | 0.35 m | marge supplémentaire ajoutée au risque max        |

Exemple pour durcir le comportement (plus prudent) :

```bash
ros2 launch kelly_nav kelly_monitor_launch.py kelly_b:=0.8 d_safe:=2.0
```

## 7. Ce qu'il faudra documenter pour la réunion

- schéma d'architecture : ajouter le nœud `kelly_monitor_node` entre
  `/scan`+`/odom` et les services `set_parameters` de `controller_server` /
  `local_costmap`
- liste des nouveaux topics : `/kelly/p_safe`, `/kelly/fraction`,
  `/kelly/ttc`, `/kelly/min_distance`, `/kelly/applied_vmax`,
  `/kelly/applied_inflation`
- la formule et le choix des seuils (justifie `d_safe`, `ttc_safe`, `kelly_b`
  par rapport à la taille/vitesse réelle de ton robot)
- courbes comparatives (étape 5 ci-dessus)
