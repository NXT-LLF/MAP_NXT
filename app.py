import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import math
from unidecode import unidecode
from rapidfuzz import process, fuzz
import time

st.markdown(
    """
    <div style='display: flex; align-items: center;'>
        <img src='https://scontent-cdg4-3.xx.fbcdn.net/v/t39.30808-6/507850690_1145471717619181_7394680818477187875_n.jpg?_nc_cat=106&ccb=1-7&_nc_sid=6ee11a&_nc_ohc=DGlwIkRgEmEQ7kNvwEwRveK&_nc_oc=AdnWUOU4skzzbyIBd7jeCVVBVPyFEgzNcrK6nup3xVkXNNW0HwQTvHR4i_EQVhV5q4U&_nc_zt=23&_nc_ht=scontent-cdg4-3.xx&_nc_gid=hsPij3kJ-y8GHpA_6yMoWQ&oh=00_AfWyt15EozDTKXg1KjdfFb1BgAAo39825gEHIyn7I3s0Xw&oe=68A20E17' style='width:60px; margin-right:15px;'>
        <h1 style='color:#ff002d; margin:0;'>MAP POLE PERF & PROCESS</h1>
    </div>
    """,
    unsafe_allow_html=True
)

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

search_input = st.text_input("Rechercher une ville (approx.) :", value="", key="ville_recherche", placeholder="Ex: Saint-Etienne, marseille, nice...")

ville_input = None

def normalize_str(s):
    return unidecode(s.lower().replace("-", " ").strip())

if search_input:
    search_clean = normalize_str(search_input)
    choices = communes_df["label_clean"].tolist()
    results = process.extract(search_clean, choices, scorer=fuzz.WRatio, limit=10)
    suggestions = [communes_df.iloc[choices.index(res[0])]["label"] for res in results if res[1] >= 50]
    if suggestions:
        ville_input = st.selectbox("Suggestions :", suggestions)
    else:
        st.warning("Aucune correspondance trouvée.")
else:
    st.info("Veuillez saisir une ville pour commencer la recherche.")

if ville_input:
    rayon = st.slider("Rayon de recherche (km) :", 1, 50, 1)
    
    if st.button("Lancer la recherche"):
        ref_data = communes_df[communes_df["label"] == ville_input].iloc[0]
        ref_coords = (ref_data["latitude"], ref_data["longitude"])

        # Progress bar à la place du spinner
        progress_bar = st.progress(0)
        df = communes_df.copy()
        for i, row in df.iterrows():
            df.at[i, "distance_km"] = geodesic(ref_coords, (row["latitude"], row["longitude"])).km
            if i % 50 == 0:  # Mise à jour périodique
                progress_bar.progress(min(i / len(df), 1.0))
        progress_bar.progress(1.0)

        communes_filtrees = df[df["distance_km"] <= rayon].copy()
        communes_filtrees["distance_km"] = communes_filtrees["distance_km"].round(1)
        communes_filtrees = communes_filtrees.sort_values("distance_km")

        st.success(f"{len(communes_filtrees)} villes trouvées.")

        # Carte
        circle_polygon = create_circle_polygon(ref_coords, rayon * 1000)
        circle_layer = pdk.Layer(
            "PolygonLayer",
            data=[{
                "polygon": circle_polygon,
                "fill_color": [173, 216, 230, 50],
                "line_color": [100, 160, 200, 150],
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
            latitude=ref_data["latitude"],
            longitude=ref_data["longitude"],
            zoom=9,
            pitch=0
        )

        st.pydeck_chart(pdk.Deck(
            layers=[circle_layer, scatter_layer],
            initial_view_state=view_state,
            map_style='light',
            tooltip={"text": "{nom}"}
        ))

        # Multiselect avant tableau
        selected_villes = st.multiselect(
            "Sélectionnez les villes à afficher",
            options=communes_filtrees["label"],
            default=communes_filtrees["label"].tolist()
        )
        final_villes = communes_filtrees[communes_filtrees["label"].isin(selected_villes)]

        # Tableau
        st.subheader("Tableau des villes")
        st.dataframe(final_villes[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

        # Zone de chalandise texte
        st.subheader(f"Zone de chalandise de {rayon} km autour de {ville_input}")
        resultat_texte = ", ".join(final_villes["code_postal"].tolist())
        st.text_area("", resultat_texte, height=100)
