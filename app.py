import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import numpy as np
import math
import folium # Nouveau package pour la carte avec des couches activables
from unidecode import unidecode
from rapidfuzz import process, fuzz
import time
# from geopy.distance import geodesic # Non utilisé, remplacé par Haversine

# --- CONFIGURATION INITIALE ---

st.set_page_config(layout="wide")

st.markdown(
    """
    <div style='display: flex; align-items: center;'>
        <img src='https://media.licdn.com/dms/image/v2/D4E0BAQEbP7lqDuz7mw/company-logo_200_200/B4EZd3054dGwAM-/0/1750062047120/nexity_logo?e=2147483647&v=beta&t=otRoz68NIpQkZ8yic15QgeeKuZHVcrXGqSUKH1YF9eg' style='width:60px; margin-right:15px;'>
        <h1 style='color:#ff002d; margin:0;'>MAP PÔLE PERF & PROCESS</h1>
    </div>
    """,
    unsafe_allow_html=True
)

# --- FONCTIONS DE GÉOMÉTRIE ET PERFORMANCE ---

def haversine_vectorized(lat1, lon1, lat2_series, lon2_series):
    """
    Calcule la distance Haversine en km entre un point (lat1, lon1) 
    et une série de points (lat2_series, lon2_series) en utilisant NumPy.
    """
    R = 6371  # Rayon moyen de la Terre en km
    lat1, lon1 = np.radians(lat1), np.radians(lon1)
    lat2_series, lon2_series = np.radians(lat2_series), np.radians(lon2_series)
    dlon = lon2_series - lon1
    dlat = lat2_series - lat1
    a = np.sin(dlat / 2.0)**2 + np.cos(lat1) * np.cos(lat2_series) * np.sin(dlon / 2.0)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c

def calculate_polygon_coords(center, radius_m, points=100):
    """Calcule les coordonnées d'un polygone circulaire."""
    lat, lon = center
    coords = []
    for i in range(points):
        angle = 2 * math.pi * i / points
        dx = radius_m * math.cos(angle)
        dy = radius_m * math.sin(angle)
        delta_lat = dy / 111320
        delta_lon = dx / (40075000 * math.cos(math.radians(lat)) / 360)
        coords.append([lon + delta_lon, lat + delta_lat])
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
            
            cp = ", ".join(list(set(cp_list))) # Nettoyage des CP redondants
            first_cp = cp_list[0] if cp_list else ""

            cleaned.append({
                "nom": c["nom"],
                "code_postal": cp,
                "latitude": lat,
                "longitude": lon,
                "label": f"{c['nom']} ({first_cp})", 
                "label_clean": normalize_str(c["nom"]),
                "cp_list": cp_list # Liste des codes postaux pour recherche
            })
        except:
            continue
            
    return pd.DataFrame(cleaned)

communes_df = get_all_communes()

if communes_df.empty:
    st.stop()

# --- RECHERCHE AMÉLIORÉE (VILLE + CODE POSTAL) ---

st.subheader("1. Définir le Point de Référence")

search_input = st.text_input(
    "Rechercher une ville ou 'Ville Code Postal' (ex: Andilly 95):", 
    value="", 
    key="ville_recherche", 
    placeholder="Ex: Saint-Etienne, Andilly 95, 69002...",
    help="Ajouter le code postal permet de lever les ambiguïtés (villes homonymes)."
)

ville_input = None

if search_input:
    search_clean = normalize_str(search_input)
    
    # Tentative de séparer Nom de Ville et Code Postal
    parts = search_input.split()
    search_name = " ".join([p for p in parts if not p.isdigit()])
    search_cp = [p for p in parts if p.isdigit() and len(p) == 5]
    
    # 1. Recherche exacte sur le Nom de Ville OU un Code Postal exact
    # Cela gère l'ambiguïté en filtrant d'abord sur le CP si fourni
    if search_cp:
        target_cp = search_cp[0]
        exact_match = communes_df[communes_df["cp_list"].apply(lambda x: target_cp in x)]
        
        if not exact_match.empty:
            if search_name:
                # Filtrer les résultats du CP par le nom si le nom est également fourni
                search_clean_name = normalize_str(search_name)
                choices = exact_match["label_clean"].tolist()
                results = process.extract(search_clean_name, choices, scorer=fuzz.WRatio, limit=10)
                suggestions = [exact_match.iloc[choices.index(res[0])]["label"] for res in results if res[1] >= 90]
            else:
                # Si seul le CP est donné, liste toutes les villes de ce CP
                suggestions = exact_match["label"].tolist()
        else:
            suggestions = []
            
    # 2. Recherche floue classique si pas de CP précis ou si la recherche CP a échoué
    if not search_cp or not suggestions:
        choices = communes_df["label_clean"].tolist()
        results = process.extract(search_clean, choices, scorer=fuzz.WRatio, limit=10)
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

# --- PRÉVISUALISATION ET CALCUL DE LA ZONE ---

ref_data = None
ref_lat, ref_lon = None, None

if ville_input:
    ref_data = communes_df[communes_df["label"] == ville_input].iloc[0]
    ref_lat, ref_lon = ref_data["latitude"], ref_data["longitude"]
    
    st.subheader("2. Définir le Rayon et Prévisualiser")
    rayon = st.slider("Rayon de recherche (km) :", 1, 50, 1)

    # Création du deck de base pour la prévisualisation (PyDeck)
    ref_coords = (ref_lat, ref_lon)
    circle_polygon_pre = calculate_polygon_coords(ref_coords, rayon * 1000)
    
    circle_layer_pre = pdk.Layer(
        "PolygonLayer",
        data=[{
            "polygon": circle_polygon_pre,
            "fill_color": [255, 165, 0, 50], # Orange léger pour prévisualisation
            "line_color": [255, 140, 0, 150],
        }],
        get_polygon="polygon",
        get_fill_color="fill_color",
        get_line_color="line_color",
        stroked=True,
        filled=True,
    )

    view_state_pre = pdk.ViewState(
        latitude=ref_lat,
        longitude=ref_lon,
        zoom=9.5 - (rayon * 0.05), # Zoom dynamique
        pitch=0
    )

    st.markdown("##### Prévisualisation de la Zone de Chalandise (Rayon actuel)")
    st.pydeck_chart(pdk.Deck(
        layers=[circle_layer_pre],
        initial_view_state=view_state_pre,
        map_style='light'
    ))

    # --- Lancement de la recherche ---
    
    with st.form("search_form"):
        st.markdown(f"**Rayon sélectionné : {rayon} km** autour de **{ville_input}**.")
        submitted = st.form_submit_button("3. Lancer la Recherche et l'Analyse 🚀")

    if submitted:
        
        # --- CALCUL DE LA ZONE OPTIMISÉ (Haversine) ---
        
        with st.spinner("Calcul des distances aux 36 000 communes (Instantané !)..."):
            communes_df["distance_km"] = haversine_vectorized(
                ref_lat, 
                ref_lon, 
                communes_df["latitude"], 
                communes_df["longitude"]
            )
            
        communes_filtrees = communes_df[communes_df["distance_km"] <= rayon].copy()
        communes_filtrees["distance_km"] = communes_filtrees["distance_km"].round(1)
        communes_filtrees = communes_filtrees.sort_values("distance_km")
        
        st.success(f"✅ {len(communes_filtrees)} villes trouvées dans la zone de {rayon} km.")

        # --- CARTE AVEC COUCHES MULTIPLES (Folium) ---
        
        st.subheader("Carte Interactive des Villes et des Données d'Analyse")

        # 1. Initialisation de la carte Folium (plus adapté pour les couches de données)
        m = folium.Map(
            location=[ref_lat, ref_lon], 
            zoom_start=int(9.5 - (rayon * 0.05)),
            tiles="CartoDB positron" # Style clair
        )

        # Couche 1: Zone de Chalandise (Polygone)
        folium.Polygon(
            locations=[(lat, lon) for lon, lat in circle_polygon_pre], # Folium attend [lat, lon]
            tooltip=f"Zone de Chalandise de {rayon} km",
            color='#FF8C00', # Dark Orange
            weight=3,
            fill=True,
            fill_color='#FFA500', # Light Orange
            fill_opacity=0.2
        ).add_to(m)

        # Couche 2: Villes de la zone (Markers)
        marker_group = folium.FeatureGroup(name="Villes dans la Zone", show=True).add_to(m)
        folium.Marker(
            location=[ref_lat, ref_lon],
            popup=f"**{ville_input}** (Point de Référence)",
            icon=folium.Icon(color='red', icon='home', prefix='fa')
        ).add_to(marker_group)
        
        for index, row in communes_filtrees.iterrows():
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]],
                radius=4,
                color='red',
                fill=True,
                fill_color='#ff002d',
                fill_opacity=0.7,
                tooltip=f"{row['nom']} ({row['code_postal'].split(',')[0]}) - {row['distance_km']} km"
            ).add_to(marker_group)


        # Couches additionnelles (Simulation d'intégration des API)
        
        # --- SIMULATION DE COUCHES D'ANALYSE ---
        
        # Le code réel nécessiterait un appel API par commune/IRIS ou le chargement
        # de GeoJSON lourds. Nous simulons l'existence des couches pour la structure.
        
        with st.expander("📊 Couches d'Analyse Géo-Marketing (Transports, DVF, INSEE)"):
            
            # Couche de Transport (Simulation)
            transport_layer = folium.FeatureGroup(name="Transports (Simulation)", show=False).add_to(m)
            # Ajouter un point d'arrêt simulé
            folium.Marker(
                location=[ref_lat + 0.05, ref_lon],
                popup="Arrêt de Bus SImulé",
                icon=folium.Icon(color='blue', icon='bus', prefix='fa')
            ).add_to(transport_layer)
            st.markdown("*(Pour une intégration réelle : les données **transport.data.gouv.fr** doivent être chargées, géocodées et converties en format Folium (ex: GeoJSON/Markers).)*")

            # Couche DVF (Simulation)
            dvf_layer = folium.FeatureGroup(name="Prix Immobiliers DVF (Simulation)", show=False).add_to(m)
            # Ajout d'une zone DVF simulée
            folium.Circle(
                location=[ref_lat - 0.05, ref_lon],
                radius=5000,
                color='#008000',
                fill=True,
                fill_color='#90EE90',
                fill_opacity=0.3,
                tooltip="Prix moyen DVF simulé (e.g., 3500€/m²)"
            ).add_to(dvf_layer)
            st.markdown("*(Pour une intégration réelle : les données **DVF** nécessitent un traitement lourd (jointure spatiale avec les IRIS ou communes).)*")

            # Couche INSEE (Simulation)
            insee_layer = folium.FeatureGroup(name="Socio-Démographie INSEE (Simulation)", show=False).add_to(m)
            folium.Marker(
                location=[ref_lat, ref_lon + 0.05],
                popup="Densité/Revenus INSEE (Simulé)",
                icon=folium.Icon(color='darkred', icon='users', prefix='fa')
            ).add_to(insee_layer)
            st.markdown("*(Pour une intégration réelle : les données **INSEE** nécessitent souvent une clé API et/ou le chargement de données socio-démographiques par commune/IRIS.)*")
        
        # --- FIN SIMULATION ---
        
        # Ajout du contrôle des couches
        folium.LayerControl().add_to(m)
        
        # Affichage de la carte Folium dans Streamlit
        st.components.v1.html(
            m._repr_html_(), 
            height=500
        )

        # --- AFFICHAGE ET EXPORT DES DONNÉES ---
        
        col_stats, col_export = st.columns([1, 2])
        
        with col_stats:
            st.subheader("Statistiques")
            st.metric(label="Commune de référence", value=ville_input)
            st.metric(label="Rayon ciblé", value=f"{rayon} km")
            st.metric(label="Villes dans la zone", value=len(communes_filtrees))
            
        with col_export:
            # Nettoyage des doublons (Point 5)
            all_cp = [cp_item.strip() for cp in communes_filtrees["code_postal"] for cp_item in cp.split(',')]
            unique_cp = list(set(all_cp))
            resultat_cp = ", ".join(unique_cp)
            
            st.subheader("Codes Postaux (Nettoyés des doublons)")
            st.text_area(
                f"Codes Postaux uniques ({len(unique_cp)} codes) :", 
                resultat_cp, 
                height=100
            )

        st.subheader("Détail des communes")
        st.dataframe(
            communes_filtrees[["nom", "code_postal", "distance_km"]].reset_index(drop=True),
            use_container_width=True
        )
