import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import numpy as np
import math
from unidecode import unidecode
from rapidfuzz import process, fuzz 

# --- IMPORT NÉCESSAIRE POUR LA FONCTION DE COPIE ---
# NOTE: Cette librairie doit être installée via pip (pip install streamlit-clipboard)
# Si vous ne pouvez pas installer de nouvelles librairies, le bouton de copie ne fonctionnera pas.
try:
    from streamlit_clipboard import st_copy_to_clipboard
except ImportError:
    def st_copy_to_clipboard(label, data):
        st.error("L'installation de la librairie 'streamlit-clipboard' est requise pour cette fonctionnalité.")


# --- CONFIGURATION ET EN-TÊTE ---

st.set_page_config(layout="wide")

# CSS personnalisé pour styliser le bouton (Point 3)
st.markdown("""
<style>
/* Centrage du titre et du logo (Point 1) */
div.stContainer > div:first-child > div:first-child > div:nth-child(2) {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
}
/* Style pour le bouton Lancer la Recherche (Point 3) */
div.stButton > button {
    background-color: #FD002D !important;
    color: white !important;
    border-radius: 0.5rem;
    font-weight: bold;
    border-color: #FD002D !important;
}
</style>
""", unsafe_allow_html=True)


# Définition des couleurs personnalisées
COLOR_ANCHOR = [130, 40, 95, 255]    # #82285f (Point d'ancrage - Point 2)
COLOR_CITIES = [200, 50, 120, 180]    # #c83278 (Magenta/Rose foncé)
COLOR_CIRCLE_LINE = [240, 220, 225, 200] # #500523 (Rayon ligne - Point 2)
COLOR_CIRCLE_FILL = [240, 220, 225, 50]  # #f0c8af (Rayon remplissage - Point 2)

# --- FONCTIONS DE GÉOMÉTRIE ET PERFORMANCE ---

def haversine_vectorized(lat1, lon1, lat2_series, lon2_series):
    """Calcule la distance Haversine en km entre un point et une série de points."""
    R = 6371
    lat1_rad, lon1_rad = np.radians(lat1), np.radians(lon1)
    lat2_series_rad, lon2_series_rad = np.radians(lat2_series), np.radians(lon2_series)
    dlon = lon2_series_rad - lon1_rad
    dlat = lat2_series_rad - lat1_rad
    a = np.sin(dlat / 2.0)**2 + np.cos(lat1_rad) * np.cos(lat2_series_rad) * np.sin(dlon / 2.0)**2
    c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    return R * c

def calculate_polygon_coords(center, radius_m, points=100):
    """Calcule les coordonnées d'un polygone circulaire pour PyDeck [lon, lat]."""
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
    # --- EN-TÊTE CENTRÉ (Point 1) ---
    st.markdown(
        """
        <div style='display: flex; align-items: center; flex-direction: column; text-align: center;'>
            <img src='https://scontent-cdg4-3.xx.fbcdn.net/v/t39.30808-6/507850690_1145471717619181_7394680818477187875_n.jpg?_nc_cat=106&ccb=1-7&_nc_sid=a5f93a&_nc_ohc=y8xhIjr4YPgQ7kNvwGej3VU&_nc_oc=AdmPx93F-yyeU7-IOLcFvujNGXaz4mBlEMOCpexvxcGHKk1LZN71Dkto3B0EfFPgQXo&_nc_zt=23&_nc_ht=scontent-cdg4-3.xx&_nc_gid=cU5o6AToXnvJleEE01KUTA&oh=00_Afj4ibgV5zJ5TigLCUVRQUL7JrJj5YJIlxQEr6FDF3Ecwg&oe=6923B197' style='width:60px; margin-right:0px; margin-bottom: 10px;'>
            <h1 style='color:#ff002d; margin:0;'>MAP PÔLE PERF & PROCESS</h1>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --- ÉTAPE 1: RECHERCHE FIABLE (Nom OU CP) ---
    st.subheader("1. Définir le Point de Référence")
    
    search_input = st.text_input(
        "Rechercher une ville ou un Code Postal:", 
        value="", 
        key="ville_recherche", 
        placeholder="Ex: Deuil la Barre ou 95170...",
        help="Saisissez soit le nom de la ville, soit le code postal à 5 chiffres."
    )

    ville_input = None
    suggestions = []

    if search_input:
        
        if len(search_input) == 5 and search_input.isdigit():
            cp_from_input = search_input
            matching_cp_df = communes_df[communes_df["cp_list"].apply(lambda x: cp_from_input in x)]
            suggestions = matching_cp_df["label"].tolist()

        else:
            search_clean = normalize_str(search_input)
            choices = communes_df["label_clean"].tolist()
            
            results = process.extract(search_clean, choices, scorer=fuzz.token_set_ratio, limit=10)
            
            scored_suggestions = []
            for res in results:
                if res[1] >= 90:
                    original_label = communes_df.iloc[communes_df["label_clean"].tolist().index(res[0])]["label"]
                    scored_suggestions.append((original_label, res[1]))
            
            scored_suggestions.sort(key=lambda x: x[1], reverse=True)
            suggestions = [label for label, score in scored_suggestions]
        
        if suggestions:
            suggestions = list(set(suggestions)) 
            ville_input = st.selectbox(
                "Sélectionnez la ville de référence :", 
                suggestions
            )
        else:
            st.warning("Aucune correspondance trouvée. Veuillez affiner la recherche.")
    else:
        st.info("Veuillez saisir une ville ou un code postal pour commencer.")

    # --- ÉTAPE 2: DÉFINITION ET CARTE ---
    
    if 'submitted' not in st.session_state:
        st.session_state['submitted'] = False

    if ville_input:
        ref_data = communes_df[communes_df["label"] == ville_input].iloc[0]
        ref_lat, ref_lon = ref_data["latitude"], ref_data["longitude"]
        ref_coords = (ref_lat, ref_lon)
        ref_cp_display = ref_data["code_postal"].split(',')[0]

        st.subheader("2. Définir le Rayon et Visualiser la Zone")
        rayon = st.slider("Rayon de recherche (km) :", 1, 50, 5, key="rayon_slider")
        
        # --- COUCHES DE BASE ---
        
        circle_polygon = calculate_polygon_coords(ref_coords, rayon * 1000)
        
        circle_layer = pdk.Layer(
            "PolygonLayer",
            data=[{
                "polygon": circle_polygon,
                "fill_color": COLOR_CIRCLE_FILL, # f0dce1
                "line_color": COLOR_CIRCLE_LINE, # f0dce1
            }],
            get_polygon="polygon",
            get_fill_color="fill_color",
            get_line_color="line_color",
            stroked=True,
            filled=True,
        )

        ref_point_layer = pdk.Layer(
            "ScatterplotLayer",
            data=pd.DataFrame([{"lon": ref_lon, "lat": ref_lat}]),
            get_position='[lon, lat]',
            get_radius=500,
            get_fill_color=COLOR_ANCHOR, # 82285f
            pickable=True, 
            tooltip={"text": f"{ville_input}\nCP: {ref_cp_display}"}
        )

        view_state = pdk.ViewState(
            latitude=ref_lat,
            longitude=ref_lon,
            zoom=9.5 - (rayon * 0.05),
            pitch=0
        )
        
        layers = [circle_layer, ref_point_layer]
        tooltip_data = {"html": f"<b>Référence: {ville_input}</b><br/>Rayon: {rayon} km"}

        # Vérification si le rayon ou la ville ont changé après la soumission
        current_inputs = (ville_input, rayon)
        last_inputs = st.session_state.get('last_inputs')
        
        if last_inputs != current_inputs:
            st.session_state['submitted'] = False
            st.session_state['last_inputs'] = current_inputs

        # Si l'état est "soumis", préparer la couche de résultats pour la carte
        if st.session_state.get("submitted"):
            
            with st.spinner(f"Calcul des distances pour {len(communes_df)} communes..."):
                communes_df["distance_km"] = haversine_vectorized(
                    ref_lat, ref_lon, communes_df["latitude"], communes_df["longitude"]
                )
            
            communes_filtrees = communes_df[communes_df["distance_km"] <= rayon].copy()
            communes_filtrees["distance_km"] = communes_filtrees["distance_km"].round(1)
            communes_filtrees = communes_filtrees.sort_values("distance_km")

            scatter_layer_result = pdk.Layer(
                "ScatterplotLayer",
                data=communes_filtrees,
                get_position='[longitude, latitude]',
                get_radius=500,
                get_fill_color=COLOR_CITIES,
                pickable=True, 
                tooltip={"text": "{nom} \n Distance: {distance_km} km \n Code Postal: {code_postal}"}
            )
            
            layers.append(scatter_layer_result)
            tooltip_data = {"html": "<b>{nom}</b><br/>Distance: {distance_km} km", 
                            "style": {"backgroundColor": "#c83278", "color": "white"}}
        
        # Affichage de la carte unique (Map au-dessus)
        st.subheader("Carte de la Zone de Chalandise")
        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=view_state,
            map_style='light',
            tooltip=tooltip_data
        ))
        
        # --- BOUTON DE LANCEMENT (Bouton en dessous de la map) ---
        submitted_button = st.button("3. Lancer la Recherche 🚀", use_container_width=True)
        
        if submitted_button:
            st.session_state["submitted"] = True
            st.rerun()

        # --- AFFICHAGE DES RÉSULTATS (Dashboard) ---
        if st.session_state.get("submitted"):

            # Recalcul rapide des données pour le dashboard (Streamlit gère le cache)
            with st.spinner(f"Finalisation des résultats..."):
                communes_df["distance_km"] = haversine_vectorized(
                    ref_lat, ref_lon, communes_df["latitude"], communes_df["longitude"]
                )
                communes_filtrees = communes_df[communes_df["distance_km"] <= rayon].copy()
                communes_filtrees["distance_km"] = communes_filtrees["distance_km"].round(1)
                communes_filtrees = communes_filtrees.sort_values("distance_km")
            
            st.markdown("---")
            st.success(f"✅ {len(communes_filtrees)} villes trouvées dans la zone de {rayon} km.")

            
            col_stats, col_export = st.columns([1, 2])

            with col_stats:
                st.subheader("Statistiques Clés")
                st.metric(label="Commune de référence", value=ville_input)
                st.metric(label="Rayon ciblé", value=f"{rayon} km")
                st.metric(label="Villes dans la zone", value=len(communes_filtrees))
            
            with col_export:
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
                
                # Bouton de copie (Point 4)
                st_copy_to_clipboard(
                    label="Copier les Codes Postaux 📋", 
                    data=resultat_cp,
                )

            with st.expander("Afficher le détail des communes trouvées"):
                st.dataframe(
                    communes_filtrees[["nom", "code_postal", "distance_km"]].reset_index(drop=True),
                    use_container_width=True
                )
