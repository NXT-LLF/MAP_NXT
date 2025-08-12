import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import math
from unidecode import unidecode
from rapidfuzz import process, fuzz

st.markdown("<h1 style='color:#ff002d;'>MAP MRKTG POLE PERF NXT</h1>", unsafe_allow_html=True)

def get_commune_info(ville_input):
    ville_input = unidecode(ville_input.lower().replace(" ", "-"))
    url = f"https://geo.api.gouv.fr/communes?nom={ville_input}&fields=nom,code,codePostal,codesPostaux,centre&format=json&geometry=centre"
    r = requests.get(url)
    data = r.json()
    if not data:
        return None
    commune = data[0]

    if "codePostal" in commune and commune["codePostal"]:
        cp = commune["codePostal"]
    elif "codesPostaux" in commune and commune["codesPostaux"]:
        cp = ", ".join(commune["codesPostaux"])
    else:
        cp = ""

    return {
        "nom": commune["nom"],
        "code_postal": cp,
        "latitude": commune["centre"]["coordinates"][1],
        "longitude": commune["centre"]["coordinates"][0]
    }

@st.cache_data
def get_all_communes():
    url = "https://geo.api.gouv.fr/communes?fields=nom,code,codePostal,codesPostaux,centre&format=json&geometry=centre"
    r = requests.get(url)
    data = r.json()
    cleaned = []
    for c in data:
        try:
            lat = c["centre"]["coordinates"][1]
            lon = c["centre"]["coordinates"][0]

            if "codePostal" in c and c["codePostal"]:
                cp = c["codePostal"]
            elif "codesPostaux" in c and c["codesPostaux"]:
                cp = ", ".join(c["codesPostaux"])
            else:
                cp = ""

            cleaned.append({
                "nom": c["nom"],
                "code_postal": cp,
                "latitude": lat,
                "longitude": lon,
                # Ajout d'une version "nettoyée" du label pour faciliter la recherche
                "label": c["nom"],
                "label_clean": unidecode(c["nom"].lower().replace("-", " ").strip())
            })
        except:
            continue
    return pd.DataFrame(cleaned)

def create_circle_polygon(center, radius_m, points=100):
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

communes_df = get_all_communes()

# Focus automatique sur la barre de recherche avec st.experimental_rerun astuce minimale :
# (on peut forcer le rerun si nécessaire, mais ici on garde simple)

# Entrée utilisateur pour recherche avec focus
search_input = st.text_input("Rechercher une ville (approx.) :", value="", key="ville_recherche", placeholder="Ex: Saint-Etienne, marseille, nice...")

ville_input = None

def normalize_str(s):
    return unidecode(s.lower().replace("-", " ").strip())

if search_input:
    search_clean = normalize_str(search_input)

    # On cherche la meilleure correspondance sur la colonne nettoyée
    choices = communes_df["label_clean"].tolist()
    results = process.extract(
        search_clean,
        choices,
        scorer=fuzz.WRatio,
        limit=10
    )
    suggestions = [communes_df.iloc[choices.index(res[0])]["label"] for res in results if res[1] >= 50]

    if suggestions:
        ville_input = st.selectbox("Suggestions :", suggestions)
    else:
        st.warning("Aucune correspondance trouvée.")
else:
    st.info("Veuillez saisir une ville pour commencer la recherche.")

if ville_input:
    rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

    ref_data = communes_df[communes_df["label"] == ville_input].iloc[0]

    ref = {
        "nom": ville_input,
        "code_postal": ref_data["code_postal"],
        "latitude": ref_data["latitude"],
        "longitude": ref_data["longitude"]
    }

    ref_coords = (ref['latitude'], ref['longitude'])

    df = communes_df.copy()

progress_bar = st.progress(0)
total = len(df)

distances = []
for i, row in enumerate(df.itertuples()):
    dist = geodesic(ref_coords, (row.latitude, row.longitude)).km
    distances.append(dist)
    if i % 50 == 0:  # Met à jour la barre toutes les 50 lignes (pour fluidité)
        progress_bar.progress(min((i+1) / total, 1.0))

df["distance_km"] = distances
communes_filtrees = df[df["distance_km"] <= rayon]
communes_filtrees = communes_filtrees.sort_values("distance_km")

progress_bar.progress(1)  # Barre à 100% à la fin

    st.success(f"{len(communes_filtrees)} villes trouvées.")

    # Carte
    st.subheader("Carte interactive")
    circle_polygon = create_circle_polygon(ref_coords, rayon * 1000)
    circle_layer = pdk.Layer(
        "PolygonLayer",
        data=[{
            "polygon": circle_polygon,
            "fill_color": [173, 216, 230, 50],
            "line_color": [173, 216, 230, 150],
        }],
        get_polygon="polygon",
        get_fill_color="fill_color",
        get_line_color="line_color",
        pickable=False,
        stroked=True,
        filled=True,
        extruded=False,
    )

    scatter_layer = pdk.Layer(
        "ScatterplotLayer",
        data=communes_filtrees,
        get_position='[longitude, latitude]',
        get_radius=500,
        get_fill_color=[255, 0, 45, 180],
        pickable=True,
    )

    view_state = pdk.ViewState(
        latitude=ref["latitude"],
        longitude=ref["longitude"],
        zoom=9,
        pitch=0
    )

    st.pydeck_chart(pdk.Deck(
        layers=[circle_layer, scatter_layer],
        initial_view_state=view_state,
        map_style='light',
        tooltip={"text": "{nom}"}
    ))

    # Sélection villes à afficher
    st.subheader("Cochez les villes à afficher sur la carte")
    selected_villes = st.multiselect(
        "Sélectionnez les villes à afficher",
        options=communes_filtrees["label"],
        default=communes_filtrees["label"].tolist()
    )

    final_villes = communes_filtrees[communes_filtrees["label"].isin(selected_villes)]

    # Tableau avec CP
    st.subheader("Résultats")
    st.dataframe(final_villes[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

    # Codes postaux à copier
    codes_postaux = final_villes["code_postal"].tolist()
    resultat_texte = ", ".join(codes_postaux)

    st.text_area("Zone de chalandise :", resultat_texte, height=100)
