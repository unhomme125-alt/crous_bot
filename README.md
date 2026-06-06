# 🏠 CROUS Housing Monitor Bot

Un bot de surveillance en temps réel pour **trouverunlogement.lescrous.fr** — détecte les nouveaux logements correspondant à vos critères et vous alerte automatiquement.

## 🚀 Installation rapide

### Prérequis
- Python 3.10+ (testé sur 3.12)
- pip

### Étapes

```bash
# 1. Cloner ou télécharger le repo
cd crous_bot

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Première utilisation : créer une config
python main.py --new-config

# 4. Lancer la surveillance
python main.py
```

## 📦 Dépendances

```
requests>=2.31          # HTTP client avec session persistante
beautifulsoup4>=4.12    # Parser HTML (pour nettoyer les textes)
rich>=13.7              # Formatage terminal (tables, couleurs, emoji)
plyer>=2.1              # Notifications de bureau (optionnel)
schedule>=1.2           # Scheduling (optionnel, non utilisé actuellement)
```

Installer : `pip install -r requirements.txt`

## 📖 Commandes complètes

### Démarrage et configuration

```bash
# Menu interactif (sélectionner ou créer une config)
python main.py

# Créer une nouvelle configuration
python main.py --new-config

# Éditer une config existante (relancer --new-config avec un nom existant)
python main.py --new-config
# → Entrer le nom d'une config existante
# → Modifier les champs
```

### Lancer la surveillance

```bash
# Avec menu interactif de sélection
python main.py

# Avec une config spécifique
python main.py --config Paris

# Vérification unique (pas de boucle)
python main.py --config Paris --once

# Intervalle personnalisé (en secondes, min 60)
python main.py --config Paris --interval 600

# Boucle + intervalle perso
python main.py --config Paris --interval 300
```

### Gestion des configurations

```bash
# Lister toutes les configs disponibles
python main.py --list

# Supprimer une config
python main.py --delete Lyon

# Affichage attendu avec --list
# Configurations disponibles :
#   • Lyon — Lyon, 500€, 10m², colocation
#   • Paris — Paris, 400€, 9m², individuel
#   • Marseille — Marseille, 350€, 8m², couple
```

## 🎯 Workflow complet (exemple)

### 1. Première utilisation

```bash
$ python main.py

# Menu interactif apparaît
Configurations disponibles :
  [aucune config trouvée]
Sélectionner une config ou créer une nouvelle: nouveau

# Setup interactif
Nom de la configuration: Paris
Ville / résidence / lieu d'études (Paris): Paris
Prix max (€ / mois) (400): 400
Surface min (m²) (9): 9
Type de cohabitation [individuel/colocation/couple] (individuel): individuel
Année universitaire [2025-2026/2026-2027] (2026-2027): 2026-2027
Intervalle de vérification (secondes, min 60) (300): 300

Config « Paris » sauvegardée
Géolocalisation de « Paris »…
Config « Paris » sauvegardée
12:34:26 — 47 résultat(s), 47 nouveau(x).

# Tableau affiché avec tous les logements trouvés
🏠 47 nouveau(x) logement(s) CROUS !
┌─────────────┬───────┬─────────┬────────┬────────┬─────────┐
│ Titre       │ Prix  │ Surface │ Ville  │ Type   │ Lien    │
├─────────────┼───────┼─────────┼────────┼────────┼─────────┤
│ STUDIO ...  │ 390€  │ 17m²    │ Paris  │ indiv. │ https://│
...
```

### 2. Deuxième utilisation

```bash
$ python main.py

Configurations disponibles :
  1. Paris — Paris, 400€, 9m², individuel

Sélectionner une config (numéro ou nom) ou créer une nouvelle: 1
# ou directement
$ python main.py --config Paris
```

### 3. Créer une 2e config (Lyon)

```bash
$ python main.py --new-config

Nom de la configuration: Lyon
Ville / résidence / lieu d'études (Paris): Lyon
Prix max (€ / mois) (400): 500
Surface min (m²) (9): 10
Type de cohabitation [individuel/colocation/couple] (individuel): colocation
Année universitaire [2025-2026/2026-2027] (2026-2027): 2026-2027
Intervalle de vérification (secondes, min 60) (300): 300

# Sauvegardé dans configs/Lyon.json
```

### 4. Utiliser différentes configs

```bash
# Surveiller Paris
python main.py --config Paris

# Vérifier Lyon une fois
python main.py --config Lyon --once

# Lister tout
python main.py --list
# Configurations disponibles :
#   • Lyon — Lyon, 500€, 10m², colocation
#   • Paris — Paris, 400€, 9m², individuel
```

## 📁 Structure du projet

```
crous_bot/
├── main.py              # Entry point + CLI + scheduler
├── config.py            # Gestion des configurations (multi-config)
├── scraper.py           # Requêtes HTTP + parsing + anti-ban
├── notifier.py          # Notifications (rich terminal + plyer desktop)
├── seen.py              # Déduplication (sauvegarde les IDs vus)
├── requirements.txt     # Dépendances Python
├── CLAUDE.md            # Spec technique détaillée
├── README.md            # Cette documentation
├── configs/             # Dossier des configurations (auto-créé)
│   ├── Paris.json
│   ├── Lyon.json
│   └── ...
├── requests.log         # Journal des requêtes HTTP (horodaté)
└── seen_listings.json   # IDs des annonces déjà vues (cache global)
```

## 🔍 Filtres disponibles

Chaque configuration accepte **5 filtres** (mirror exact du site CROUS) :

| Filtre | Type | Exemple |
|--------|------|---------|
| **Ville** | Texte libre | "Paris", "Lyon", "Marseille", ou "Résidence Jean Moulin" |
| **Prix max** | Euros/mois | 400, 500, 600 |
| **Surface min** | m² | 9, 10, 15 |
| **Type cohabitation** | enum | `individuel`, `colocation`, ou `couple` |
| **Année académique** | enum | `2025-2026` ou `2026-2027` |

## 🛡️ Sécurité (anti-ban)

Le bot respecte strictement les contraintes pour éviter les bannissements :

✅ **Implémenté** :
- Délai minimum **45–90 secondes** (aléatoire) entre les requêtes
- Rotation des **User-Agents** (12 navigateurs réels différents)
- **Session HTTP persistante** + homepage warmup
- **Backoff exponentiel** (120s → 240s → 480s) sur HTTP 429/503
- **Retry limité** (3 tentatives max) sur erreurs de connexion
- **Arrêt immédiat** à la détection de CAPTCHA
- **Toutes les requêtes loggées** dans `requests.log` (horodatées)
- **Intervalle minimum 60s** (imposé, impossible d'aller plus vite)

## 💾 Persistance et cache

### `configs/` — Stockage des configurations
Chaque config est un fichier JSON indépendant :
```json
{
  "ville": "Paris",
  "prix_max": 400,
  "surface_min": 9,
  "type_cohabitation": "individuel",
  "annee": "2026-2027",
  "interval_seconds": 300,
  "bounds": { "top_left": {...}, "bottom_right": {...} }
}
```

### `seen_listings.json` — Déduplication globale
Sauvegarde les IDs des annonces déjà alertées pour **ne pas les re-notifier** :
```json
["37", "56", "79", "152", ...]
```

**Réinitialiser le cache** (pour re-voir toutes les annonces) :
```bash
rm seen_listings.json
```

### `requests.log` — Audit des requêtes
Chaque requête est loggée avec timestamp + status :
```
2026-06-06 12:06:54,650 INFO GET https://trouverunlogement.lescrous.fr/photon/api -> 200
2026-06-06 12:06:54,652 INFO THROTTLE sleeping 49.2s to respect min request gap
2026-06-06 12:07:43,943 INFO GET https://trouverunlogement.lescrous.fr/ -> 200
2026-06-06 12:09:08,360 INFO POST https://trouverunlogement.lescrous.fr/api/fr/search/45 -> 200
```

## 🔔 Notifications

### Terminal (rich)
Chaque nouvelle annonce s'affiche dans un tableau avec :
- **Titre** et résidence
- **Prix** mensuel (€)
- **Surface** (m²)
- **Ville**
- **Type** (individuel / colocation / couple)
- **Lien** direct vers l'annonce

### Bureau (optionnel)
Une notification système apparaît si **plyer** est disponible (affiche le 1er logement + nombre d'autres).

## ⚙️ Configuration avancée

### Intervalle personnalisé

```bash
# Par defaut: 300 secondes (5 minutes)
python main.py --config Paris

# Surcharger à 600 secondes (10 minutes)
python main.py --config Paris --interval 600

# + jitter: intervalle_réel = 600 + random(0,30)
# → entre 600 et 630 secondes
```

**Minimum** : 60 secondes (imposé pour la sécurité).

### Éditer une config manuellement

```bash
# Ouvrir configs/Paris.json dans votre éditeur
vim configs/Paris.json

# Exemple : changer les filtres
{
  "ville": "Lyon",           # ← changé de Paris à Lyon
  "prix_max": 500,           # ← changé de 400 à 500
  "surface_min": 10,
  "type_cohabitation": "colocation",
  "annee": "2026-2027",
  "interval_seconds": 300,
  "bounds": null             # ← pour forcer un ré-géocodage au prochain lancement
}
```

## 🐛 Dépannage

| Problème | Solution |
|---|---|
| **Aucune config au démarrage** | `python main.py --new-config` |
| **Config introuvable** | `python main.py --list` pour voir les noms disponibles |
| **Pas de nouvelles annonces** | Supprimez `seen_listings.json` pour réinitialiser le cache |
| **"interval_seconds < 60" erreur** | C'est un minimum imposé pour la sécurité |
| **Notifications plyer ne s'affichent pas** | C'est optionnel ; le terminal affichera toujours les résultats |
| **CAPTCHA détecté, bot arrêté** | Le site vous a bloqué ; attendez 1–2h, puis relancez |

## 📝 Exemple complet d'utilisation

```bash
# 1. Installation
pip install -r requirements.txt

# 2. Créer 3 configs
python main.py --new-config  # Paris
python main.py --new-config  # Lyon
python main.py --new-config  # Marseille

# 3. Lister
python main.py --list

# 4. Surveiller Paris en boucle (5 min d'intervalle)
python main.py --config Paris

# 5. Tandis qu'il tourne, dans un autre terminal, vérifier Lyon une fois
python main.py --config Lyon --once

# 6. Supprimer Marseille
python main.py --delete Marseille
```

## 🔗 Ressources

- **Site CROUS** : https://trouverunlogement.lescrous.fr
- **Spec technique** : voir `CLAUDE.md`
- **Dépendances** : voir `requirements.txt`

## 📄 Licence

À définir (dépend de vos besoins).

---

**Besoin d'aide ?** Consultez `CLAUDE.md` pour les détails architecturaux ou lancez `python main.py --help`.
