import streamlit as st
import requests
import pandas as pd
import numpy as np
import math
import folium
from unidecode import unidecode
from rapidfuzz import process, fuzz
from streamlit_folium import st_folium # Recommandé pour une meilleure intégration Folium

# --- CONFIGURATION INITIALE ---

# Le set_page_config doit rester en début de script, mais le contenu sera centré dans un container.
st.set_page_config(layout="wide")

# --- FONCTIONS DE GÉOMÉTRIE ET PERFORMANCE ---

def haversine_vectorized(lat1, lon1, lat2_series, lon2_series):
    """Calcule la distance Haversine en km entre un point et une série de points."""
    R = 6371
    lat1, lon1 = np.radians(lat1), np.radians(lon1)
    lat2_series, lon2_series = np.radians(lat2_series), np.radians(lon2_series)
    dlon = lat2_series - lat1
    dlat = lon2_series - lon1
    a = np.sin(dlat / 2.0)**2 + np.cos(lat1) * np.cos(lat2_series) * np.sin(dlon / 2.0)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c

def calculate_polygon_coords(center, radius_m, points=100):
    """Calcule les coordonnées d'un polygone circulaire pour Folium."""
    lat, lon = center
    coords = []
    # Reste en coordonnées [lon, lat] pour le calcul, puis inversé pour Folium
    for i in range(points):
        angle = 2 * math.pi * i / points
        dx = radius_m * math.cos(angle)
        dy = radius_m * math.sin(angle)
        delta_lat = dy / 111320
        delta_lon = dx / (40075000 * math.cos(math.radians(lat)) / 360)
        coords.append([lat + delta_lat, lon + delta_lon]) # Folium attend [lat, lon]
    return coords

def normalize_str(s):
    """Normalise une chaîne de caractères pour la recherche."""
    return unidecode(s.lower().replace("-", " ").strip())

# --- FONCTION DE CHARGEMENT DE DONNÉES (MISE EN CACHE) ---

@st.cache_data
def get_all_communes():
    """Charge toutes les communes françaises depuis l'API Gouv."""
    url = "https://geo.api.gouv.fr/communes?fields=nom,code,codePostal,codesPostaux,centre&format=json&geometry=centre"
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Erreur de connexion à l'API Gouv : {e}")
        return pd.DataFrame()

    cleaned = []
    for c in data:
        try:
            lat = c["centre"]["coordinates"][1]
            lon = c["centre"]["coordinates"][0]
            cp_list = []
            if "codePostal" in c and c["codePostal"]:
                cp_list.append(c["codePostal"])
            if "codesPostaux" in c and c["codesPostaux"]:
                cp_list.extend(c["codesPostaux"])
            
            cp = ", ".join(list(set(cp_list)))
            first_cp = cp_list[0] if cp_list else ""

            cleaned.append({
                "nom": c["nom"],
                "code_postal": cp,
                "latitude": lat,
                "longitude": lon,
                "label": f"{c['nom']} ({first_cp})", 
                "label_clean": normalize_str(c["nom"]),
                "cp_list": [str(c) for c in list(set(cp_list))] # Liste des codes postaux
            })
        except:
            continue
            
    return pd.DataFrame(cleaned)

communes_df = get_all_communes()

if communes_df.empty:
    st.stop()

# --- BLOC DE CONTENU CENTRÉ ---
# Point 1: Centrage des éléments
with st.container(border=False):
    col_empty_left, col_content, col_empty_right = st.columns([1, 4, 1])

with col_content:
    # --- EN-TÊTE ---
    st.markdown(
        """
        <div style='display: flex; align-items: center;'>
            <img src='https://media.licdn.com/dms/image/v2/D4E0BAQEbP7lqDuz7mw/company-logo_200_200/B4EZd3054dGwAM-/0/1750062047120/nexity_logo?e=2147483647&v=beta&t=otRoz68NIqQkZ8yic15QgeeKuZHVcrXGqSUKH1YF9eg' style='width:60px; margin-right:15px;'>
            <h1 style='color:#ff002d; margin:0;'>MAP PÔLE PERF & PROCESS</h1>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --- ÉTAPE 1: RECHERCHE AMÉLIORÉE ---
    st.subheader("1. Définir le Point de Référence")
    
    search_input = st.text_input(
        "Rechercher une ville ou 'Ville Code Postal' (ex: Andilly 95):", 
        value="", 
        key="ville_recherche", 
        placeholder="Ex: Saint-Etienne, Andilly 95, 69002...",
        help="L'ajout du code postal permet de garantir le bon choix en cas d'homonymie."
    )

    ville_input = None

    if search_input:
        search_clean = normalize_str(search_input)
        
        # Tentative de détecter le Code Postal à la fin de la chaîne
        cp_from_input = None
        if len(search_input.split()[-1]) == 5 and search_input.split()[-1].isdigit():
            cp_from_input = search_input.split()[-1]
            search_name_part = " ".join(search_input.split()[:-1])
            search_clean = normalize_str(search_name_part)
        
        suggestions = []
        
        # Point 2: Priorité absolue à la recherche CP + Nom
        if cp_from_input:
            # Recherche exacte sur la liste des codes postaux
            matching_cp_df = communes_df[communes_df["cp_list"].apply(lambda x: cp_from_input in x)]
            
            if not matching_cp_df.empty:
                # Si le nom de la ville est donné en plus du CP
                if search_clean:
                    choices = matching_cp_df["label_clean"].tolist()
                    results = process.extract(search_clean, choices, scorer=fuzz.WRatio, limit=5)
                    # Seuil très strict (95) pour les homonymes + CP
                    suggestions = [matching_cp_df.iloc[choices.index(res[0])]["label"] for res in results if res[1] >= 95]
                else:
                    # Si seul le CP est donné, liste toutes les villes de ce CP
                    suggestions = matching_cp_df["label"].tolist()
                    
        # Recherche floue fallback
        if not suggestions and search_clean:
            choices = communes_df["label_clean"].tolist()
            results = process.extract(search_clean, choices, scorer=fuzz.WRatio, limit=10)
            # Seuil de 80 pour la recherche floue générale
            suggestions = [
                communes_df.iloc[choices.index(res[0])]["label"] 
                for res in results if res[1] >= 80
            ]
        
        if suggestions:
            ville_input = st.selectbox(
                "Sélectionnez la ville de référence :", 
                suggestions
            )
        else:
            st.warning("Aucune correspondance trouvée. Veuillez affiner la recherche.")
    else:
        st.info("Veuillez saisir une ville ou un code postal pour commencer.")

    # --- ÉTAPE 2: PRÉVISUALISATION DU RAYON ET CARTE UNIQUE ---
    
    ref_data = None
    ref_lat, ref_lon = None, None

    if ville_input:
        ref_data = communes_df[communes_df["label"] == ville_input].iloc[0]
        ref_lat, ref_lon = ref_data["latitude"], ref_data["longitude"]
        ref_coords = (ref_lat, ref_lon)
        
        st.subheader("2. Définir le Rayon et Prévisualiser la Zone")
        rayon = st.slider("Rayon de recherche (km) :", 1, 50, 5, key="rayon_slider")

        # --- CARTE FOLIUM : PRÉVISUALISATION ET RÉSULTAT FINAL ---
        # Point 3: Carte Unique
        m = folium.Map(
            location=[ref_lat, ref_lon], 
            zoom_start=int(9.5 - (rayon * 0.05)),
            tiles="CartoDB positron"
        )
        
        # Prévisualisation: Couche Zone de Chalandise
        circle_coords = calculate_polygon_coords(ref_coords, rayon * 1000)
        folium.Polygon(
            locations=circle_coords, 
            tooltip=f"Zone de Chalandise de {rayon} km (Prévisualisation)",
            color='#FF8C00', 
            weight=2,
            fill=True,
            fill_color='#FFA500', 
            fill_opacity=0.1
        ).add_to(m)

        # Marqueur de référence
        folium.Marker(
            location=[ref_lat, ref_lon],
            popup=f"**{ville_input}** (Référence)",
            icon=folium.Icon(color='red', icon='home', prefix='fa')
        ).add_to(m)

        # --- Lancement de la recherche ---
        
        submitted = st.button("3. Lancer la Recherche et l'Analyse 🚀", use_container_width=True)

        # --- LOGIQUE DE CALCUL ET AFFICHAGE ---
        
        if submitted:
            
            # Calcul de la zone OPTIMISÉ (Haversine)
            with st.spinner(f"Calcul des distances pour {len(communes_df)} communes..."):
                communes_df["distance_km"] = haversine_vectorized(
                    ref_lat, ref_lon, communes_df["latitude"], communes_df["longitude"]
                )
            
            communes_filtrees = communes_df[communes_df["distance_km"] <= rayon].copy()
            communes_filtrees["distance_km"] = communes_filtrees["distance_km"].round(1)
            communes_filtrees = communes_filtrees.sort_values("distance_km")
            
            st.success(f"✅ {len(communes_filtrees)} villes trouvées dans la zone de {rayon} km.")

            # Couche Villes Filtrées (Ajoutée APRÈS le calcul)
            villes_group = folium.FeatureGroup(name="Villes dans la Zone", show=True).add_to(m)
            for index, row in communes_filtrees.iterrows():
                folium.CircleMarker(
                    location=[row["latitude"], row["longitude"]],
                    radius=3,
                    color='#ff002d',
                    fill=True,
                    fill_color='#ff002d',
                    fill_opacity=0.8,
                    tooltip=f"{row['nom']} ({row['code_postal'].split(',')[0]}) - {row['distance_km']} km"
                ).add_to(villes_group)

            # --- Couches d'Analyse (Point 4: Mapbox/Couches) ---
            
            # Couche 1: Prix M² (DVF - Simulation Heatmap/Tuiles)
            dvf_layer = folium.FeatureGroup(name="Prix M² DVF (Simulé)", show=False).add_to(m)
            # Simuler des zones de prix avec une couleur (exemple de tuilage minimaliste)
            dvf_color_map = {0.2: '#FFEDA0', 0.5: '#FEB24C', 0.8: '#FC4E2A', 1.0: '#E31A1C'}
            for index, row in communes_filtrees.sample(min(20, len(communes_filtrees))).iterrows():
                price_sim = np.random.rand() # Simuler le niveau de prix
                color = next(c for level, c in dvf_color_map.items() if price_sim < level)
                folium.Circle(
                    location=[row["latitude"], row["longitude"]],
                    radius=200, # Petite taille pour tuiles minimalistes
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.6,
                    tooltip=f"Prix M² Simulé: {int(price_sim * 4000) + 2000} €/m²"
                ).add_to(dvf_layer)
            
            # Couche 2: Transports (Simulation Lignes/Arrêts minimalistes)
            transport_layer = folium.FeatureGroup(name="Lignes/Arrêts Transports (Simulé)", show=False).add_to(m)
            # Arrêts simulés
            folium.Marker(
                location=[ref_lat + 0.01, ref_lon + 0.01],
                popup="Arrêt de Bus Simulé",
                icon=folium.Icon(color='blue', icon='bus', prefix='fa')
            ).add_to(transport_layer)
            # Ligne simulée (minimaliste)
            folium.PolyLine(
                locations=[[ref_lat, ref_lon], [ref_lat + 0.01, ref_lon + 0.01], [ref_lat + 0.02, ref_lon]],
                color="blue",
                weight=3,
                opacity=0.7,
                tooltip="Ligne de Transport Sim."
            ).add_to(transport_layer)

            # Ajout du contrôle des couches
            folium.LayerControl().add_to(m)
            
        
        # Affichage de la carte (que la recherche soit lancée ou non)
        st_folium(m, width=900, height=500, key="folium_map", returned_objects=[])

        if submitted:
            st.markdown("---")
            
            # --- AFFICHAGE ET EXPORT DES DONNÉES (Point 5: Dashboard/Statistiques) ---
            
            col_stats, col_export = st.columns([1, 2])

            with col_stats:
                st.subheader("Statistiques Clés")
                st.metric(label="Commune de référence", value=ville_input)
                st.metric(label="Rayon ciblé", value=f"{rayon} km")
                st.metric(label="Villes dans la zone", value=len(communes_filtrees))
            
            with col_export:
                # Nettoyage des doublons
                all_cp = [cp_item.strip() for cp in communes_filtrees["code_postal"] for cp_item in cp.split(',')]
                unique_cp = list(set(all_cp))
                resultat_cp = ", ".join(unique_cp)
                
                st.subheader("Codes Postaux Uniques (Nettoyés)")
                # Agrandissement du bloc codes postaux (Point 5)
                st.text_area(
                    f"Codes Postaux uniques ({len(unique_cp)} codes) :", 
                    resultat_cp, 
                    height=150,
                    help="Copiez cette liste pour l'utiliser dans vos outils marketing."
                )

            # Détail des communes masqué par défaut (Point 5)
            with st.expander("Afficher le détail des communes trouvées"):
                st.dataframe(
                    communes_filtrees[["nom", "code_postal", "distance_km"]].reset_index(drop=True),
                    use_container_width=True
                )
        
        # Affichage de la carte seule tant que la recherche n'est pas lancée
        if not submitted:
            st_folium(m, width=900, height=500, key="folium_map_pre", returned_objects=[])

# --- FIN DU BLOC CENTRÉ ---
