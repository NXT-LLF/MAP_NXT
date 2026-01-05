import streamlit as st
import requests
import pandas as pd
import pydeck as pdk
import numpy as np
import math
from unidecode import unidecode
from rapidfuzz import process, fuzz 

# --- CONFIGURATION ET EN-TÊTE ---

st.set_page_config(layout="wide")

# CSS personnalisé pour le style du bouton
st.markdown("""
<style>
/* Centrage du titre et du logo */
div.stContainer > div:first-child > div:first-child > div:nth-child(2) {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
}
/* Style pour le bouton Lancer la Recherche */
div.stButton > button {
    background-color: #FD002D !important;
    color: white !important;
    border-radius: 0.5rem;
    font-weight: bold;
    border-color: #FD002D !important;
}

/* Cache l'icône de la zone de texte pour les CP et autres ajustements */
div[data-testid="stTextarea"] > label {
    display: none;
}
</style>
""", unsafe_allow_html=True)


# Définition des couleurs personnalisées
COLOR_ANCHOR = [253, 0, 45, 255]      # #FD002D (Point d'ancrage)
COLOR_CITIES = [200, 50, 120, 180]    # #c83278 (Villes filtrées)
COLOR_CIRCLE_LINE = [80, 5, 35, 200]    # #500523 (Rayon contour)
COLOR_CIRCLE_FILL = [240, 200, 175, 50]  # #f0c8af (Rayon remplissage)

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
    """
    Calcule les coordonnées d'un polygone circulaire pour PyDeck [lon, lat].
    Correction: Utilisation de delta_lon dans la formule de longitude.
    """
    lat, lon = center
    coords = []
    for i in range(points):
        angle = 2 * math.pi * i / points
        dx = radius_m * math.cos(angle)
        dy = radius_m * math.sin(angle)
        # 1 degré de latitude est environ 111.32 km
        delta_lat = dy / 111320
        # 1 degré de longitude dépend de la latitude
        delta_lon = dx / (40075000 * math.cos(math.radians(lat)) / 360)
        
        # CORRECTION APPLIQUÉE ICI: on utilise bien delta_lon pour la longitude
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
            
            all_cps = c.get("codesPostaux", [])
            if "codePostal" in c and c["codePostal"] not in all_cps:
                 all_cps.insert(0, c["codePostal"])
            
            cp = ", ".join(list(set(all_cps)))
            first_cp = all_cps[0] if all_cps else ""

            cleaned.append({
                "nom": c["nom"],
                "code_postal": cp,
                "latitude": lat,
                "longitude": lon,
                "label": f"{c['nom']} ({first_cp})", 
                "label_clean": normalize_str(c["nom"]),
                "cp_list": [str(c) for c in list(set(all_cps))],
                "first_cp_int": int(first_cp) if first_cp.isdigit() else 99999
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
    # --- EN-TÊTE CENTRÉ ---
    st.markdown(
        """
        <div style='display: flex; align-items: center; flex-direction: column; text-align: center;'>
            <img src='https://bddnxt.my.canva.site/_assets/media/442de89eb7b0878575cdb604c5767b62.png' style='width:60px; margin-right:0px; margin-bottom: 10px;'>
            <h1 style='color:#ff002d; margin:0;'>MAP PÔLE PERF & PROCESS</h1>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --- ÉTAPE 1: RECHERCHE FIABLE (Nom OU CP) ---
    st.subheader("Définir le point de référence")
    
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
            # Recherche stricte par code postal
            cp_from_input = search_input
            matching_cp_df = communes_df[communes_df["cp_list"].apply(lambda x: cp_from_input in x)]
            suggestions = matching_cp_df["label"].tolist()

        else:
            # Recherche robuste par Nom de Ville
            search_clean = normalize_str(search_input)
            choices = communes_df["label_clean"].tolist()
            
            results = process.extract(search_clean, choices, scorer=fuzz.token_set_ratio, limit=20)
            
            scored_suggestions = []
            for res_clean, score, index in results:
                if score >= 90:
                    data = communes_df.iloc[index]
                    # Score de similarité du nom exact 
                    exact_name_score = fuzz.ratio(search_clean, normalize_str(data['nom']))
                    
                    # Clé de tri composite: (Score, Priorité CP)
                    sort_key = (score, exact_name_score, 100000 - data["first_cp_int"])
                    
                    scored_suggestions.append((data["label"], sort_key))
            
            # Trier par clé de tri
            scored_suggestions.sort(key=lambda x: x[1], reverse=True)
            suggestions = [label for label, sort_key in scored_suggestions]
        
        if suggestions:
            suggestions = list(dict.fromkeys(suggestions)) # Dé-duplication tout en gardant l'ordre
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

        st.subheader("Définir le rayon et visualiser la zone")
        rayon = st.slider("Rayon de recherche (km) :", 1, 50, 5, key="rayon_slider")
        
        # --- COUCHES DE BASE ---
        
        # La fonction calculate_polygon_coords est maintenant corrigée
        circle_polygon = calculate_polygon_coords(ref_coords, rayon * 1000) 
        
        circle_layer = pdk.Layer(
            "PolygonLayer",
            data=[{
                "polygon": circle_polygon,
                "fill_color": COLOR_CIRCLE_FILL, 
                "line_color": COLOR_CIRCLE_LINE, 
            }],
            get_polygon="polygon",
            get_fill_color="fill_color",
            get_line_color="line_color",
            stroked=True,
            filled=True,
        )

        # Rétablissement du point d'ancrage (Point 2)
        ref_point_layer = pdk.Layer(
            "ScatterplotLayer",
            data=pd.DataFrame([{"lon": ref_lon, "lat": ref_lat}]),
            get_position='[lon, lat]',
            get_radius=500,
            get_fill_color=COLOR_ANCHOR, # FD002D
            pickable=True, 
            tooltip={"text": f"Ancrage: {ville_input}\nCP: {ref_cp_display}"}
        )

        layers = [circle_layer, ref_point_layer]
        tooltip_data = {"html": f"<b>Référence: {ville_input}</b><br/>CP: {ref_cp_display}"}

        view_state = pdk.ViewState(
            latitude=ref_lat,
            longitude=ref_lon,
            zoom=9.5 - (rayon * 0.05),
            pitch=0
        )
        
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
                # Tooltip affiche Nom et Code Postal 
                tooltip={"text": "{nom} \n Code Postal: {code_postal}"} 
            )
            
            layers.append(scatter_layer_result)
            tooltip_data = {"html": "<b>{nom}</b><br/>CP: {code_postal}", 
                            "style": {"backgroundColor": "#c83278", "color": "white"}}
        
        # Affichage de la carte unique (Map au-dessus)
        st.subheader("Zone de chalandise")
        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=view_state,
            map_style='light',
            tooltip=tooltip_data
        ))
        
        # --- BOUTON DE LANCEMENT (Bouton en dessous de la map) ---
        submitted_button = st.button("3. LANCER LA RECHERCHE 🔍", use_container_width=True)
        
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
                st.subheader("Statistiques clés")
                st.metric(label="Commune de référence", value=ville_input)
                st.metric(label="Rayon ciblé", value=f"{rayon} km")
                st.metric(label="Villes dans la zone", value=len(communes_filtrees))
            
            with col_export:
                all_cp = [cp_item.strip() for cp in communes_filtrees["code_postal"] for cp_item in cp.split(',')]
                unique_cp = list(set(all_cp))
                resultat_cp = ", ".join(unique_cp)
                
                st.subheader("Codes Postaux Uniques")
                
                # Zone de texte pour les codes postaux (sans bouton de copie)
                st.text_area(
                    f"Codes Postaux nettoyés ({len(unique_cp)} CP uniques) :", 
                    resultat_cp, 
                    height=150,
                    key="cp_result_area",
                    help="Copiez cette liste pour l'utiliser dans vos outils marketing."
                )

            with st.expander("Afficher le détail des communes trouvées"):
                st.dataframe(
                    communes_filtrees[["nom", "code_postal", "distance_km"]].reset_index(drop=True),
                    use_container_width=True
                )
