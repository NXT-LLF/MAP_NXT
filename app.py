import streamlit as st
import requests
import pandas as pd
import numpy as np
import math
import folium
from unidecode import unidecode
from rapidfuzz import process, fuzz
from streamlit_folium import st_folium # Pour une meilleure intégration Folium

# --- CONFIGURATION INITIALE ---

st.set_page_config(layout="wide")

# --- FONCTIONS DE GÉOMÉTRIE ET PERFORMANCE ---

def haversine_vectorized(lat1, lon1, lat2_series, lon2_series):
    """
    Calcule la distance Haversine en km entre un point (lat1, lon1) 
    et une série de points (lat2_series, lon2_series) en utilisant NumPy.
    Correction : lat/lon et dlat/dlon ont été corrigés pour être dans le bon ordre.
    """
    R = 6371 # Rayon moyen de la Terre en km

    lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
    lat2_series_rad, lon2_series_rad = np.radians(lat2_series), np.radians(lon2_series)
    
    # CALCUL CORRIGÉ
    dlon = lon2_series_rad - lon1_rad
    dlat = lat2_series_rad - lat1_rad

    a = np.sin(dlat / 2.0)**2 + np.cos(lat1_rad) * np.cos(lat2_series_rad) * np.sin(dlon / 2.0)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    
    return R * c

def calculate_polygon_coords(center, radius_m, points=100):
    """Calcule les coordonnées d'un polygone circulaire pour Folium."""
    lat, lon = center
    coords = []
    # Folium attend [lat, lon]
    for i in range(points):
        angle = 2 * math.pi * i / points
        dx = radius_m * math.cos(angle)
        dy = radius_m * math.sin(angle)
        delta_lat = dy / 111320
        delta_lon = dx / (40075000 * math.cos(math.radians(lat)) / 360)
        coords.append([lat + delta_lat, lon + delta_lon]) 
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
                "cp_list": [str(c) for c in list(set(cp_list))]
            })
        except:
            continue
            
    return pd.DataFrame(cleaned)

communes_df = get_all_communes()

if communes_df.empty:
    st.stop()

# --- BLOC DE CONTENU CENTRÉ ---
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
        
        cp_from_input = None
        if len(search_input.split()[-1]) == 5 and search_input.split()[-1].isdigit():
            cp_from_input = search_input.split()[-1]
            search_name_part = " ".join(search_input.split()[:-1])
            search_clean = normalize_str(search_name_part)
        
        suggestions = []
        
        # LOGIQUE DE RECHERCHE CORRIGÉE ET AFFINÉE (Point 1)
        if cp_from_input:
            matching_cp_df = communes_df[communes_df["cp_list"].apply(lambda x: cp_from_input in x)]
            
            if not matching_cp_df.empty:
                if search_clean:
                    choices = matching_cp_df["label_clean"].tolist()
                    results = process.extract(search_clean, choices, scorer=fuzz.WRatio, limit=5)
                    # Utiliser le label complet, pas seulement le label_clean
                    suggestions = [matching_cp_df.iloc[communes_df["label_clean"].tolist().index(res[0])]["label"] for res in results if res[1] >= 95]
                else:
                    suggestions = matching_cp_df["label"].tolist()
                    
        if not suggestions: # Recherche floue fallback si pas de CP précis ou échec
            choices = communes_df["label_clean"].tolist()
            results = process.extract(search_clean, choices, scorer=fuzz.WRatio, limit=10)
            suggestions = [
                communes_df.iloc[communes_df["label_clean"].tolist().index(res[0])]["label"] 
                for res in results if res[1] >= 80
            ]
        
        if suggestions:
            # Nettoyer les doublons dans les suggestions elles-mêmes
            suggestions = list(set(suggestions)) 
            ville_input = st.selectbox(
                "Sélectionnez la ville de référence :", 
                suggestions
            )
        else:
            st.warning("Aucune correspondance trouvée. Veuillez affiner la recherche.")
    else:
        st.info("Veuillez saisir une ville ou un code postal pour commencer.")

    # --- ÉTAPE 2: PRÉVISUALISATION ET CARTE UNIQUE ---
    
    ref_data = None
    ref_lat, ref_lon = None, None

    if ville_input:
        ref_data = communes_df[communes_df["label"] == ville_input].iloc[0]
        ref_lat, ref_lon = ref_data["latitude"], ref_data["longitude"]
        ref_coords = (ref_lat, ref_lon)
        
        st.subheader("2. Définir le Rayon et Prévisualiser la Zone")
        rayon = st.slider("Rayon de recherche (km) :", 1, 50, 5, key="rayon_slider")
        
        # Initialisation de la carte (Point 2: Carte Unique)
        m = folium.Map(
            location=[ref_lat, ref_lon], 
            zoom_start=int(9.5 - (rayon * 0.05)),
            tiles="CartoDB positron"
        )
        
        # Couche Zone de Chalandise (Prévisualisation)
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

        # Point d'ancrage simple (Point 2: Retrait du logo)
        folium.CircleMarker(
            location=[ref_lat, ref_lon],
            radius=5,
            color='#FF8C00', # Même couleur que la bordure du rayon
            fill=True,
            fill_color='#FF8C00', 
            fill_opacity=1.0,
            tooltip=f"**{ville_input}** (Référence)"
        ).add_to(m)

        # --- Lancement de la recherche ---
        
        submitted = st.button("3. Lancer la Recherche et l'Analyse 🚀", use_container_width=True)

        # --- LOGIQUE DE CALCUL ET AFFICHAGE ---
        
        communes_filtrees = pd.DataFrame()
        if submitted:
            
            # Calcul de la zone OPTIMISÉ (Haversine corrigée)
            with st.spinner(f"Calcul des distances pour {len(communes_df)} communes..."):
                communes_df["distance_km"] = haversine_vectorized(
                    ref_lat, ref_lon, communes_df["latitude"], communes_df["longitude"]
                )
            
            # Filtrage (Point 3: Correction des résultats hors rayon)
            communes_filtrees = communes_df[communes_df["distance_km"] <= rayon].copy()
            communes_filtrees["distance_km"] = communes_filtrees["distance_km"].round(1)
            communes_filtrees = communes_filtrees.sort_values("distance_km")
            
            st.success(f"✅ {len(communes_filtrees)} villes trouvées dans la zone de {rayon} km.")

            # Couche Villes Filtrées
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

            # Ajout du contrôle des couches (seulement les villes filtrées)
            folium.LayerControl().add_to(m)

        
        # Affichage de la carte (Point 2: Appelé une seule fois)
        st_folium(m, width=900, height=500, key="folium_map", returned_objects=[])

        if submitted:
            st.markdown("---")
            
            # --- AFFICHAGE ET EXPORT DES DONNÉES ---
            
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
                st.text_area(
                    f"Codes Postaux uniques ({len(unique_cp)} codes) :", 
                    resultat_cp, 
                    height=150,
                    help="Copiez cette liste pour l'utiliser dans vos outils marketing."
                )

            # Détail des communes masqué par défaut
            with st.expander("Afficher le détail des communes trouvées"):
                st.dataframe(
                    communes_filtrees[["nom", "code_postal", "distance_km"]].reset_index(drop=True),
                    use_container_width=True
                )
