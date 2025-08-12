import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import math
from unidecode import unidecode
from streamlit_folium import st_folium
import folium

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
                "label": f'{c["nom"]}'
            })
        except:
            continue
    return pd.DataFrame(cleaned)

communes_df = get_all_communes()

ville_input = st.selectbox(
    "Rechercher la ville de référence :",
    options=communes_df["label"].tolist(),
    index=int(communes_df[communes_df["nom"].str.lower() == "paris"].index[0])
)

rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

ref_nom = ville_input
ref_data = communes_df[communes_df["label"] == ville_input].iloc[0]
ref = {
    "nom": ref_nom,
    "code_postal": ref_data["code_postal"],
    "latitude": ref_data["latitude"],
    "longitude": ref_data["longitude"]
}
ref_coords = (ref['latitude'], ref['longitude'])

with st.spinner('Calcul en cours...'):
    df = communes_df.copy()
    df["distance_km"] = df.apply(
        lambda row: geodesic(ref_coords, (row["latitude"], row["longitude"])).km,
        axis=1
    )
    communes_filtrees = df[df["distance_km"] <= rayon].sort_values("distance_km")

st.success(f"{len(communes_filtrees)} villes trouvées.")

# Initialisation des villes sélectionnées
if "selected_villes" not in st.session_state:
    st.session_state.selected_villes = communes_filtrees["nom"].tolist()

# Carte Folium
m = folium.Map(location=[ref["latitude"], ref["longitude"]], zoom_start=10)

# Cercle de recherche
folium.Circle(
    radius=rayon * 1000,
    location=[ref["latitude"], ref["longitude"]],
    color="blue",
    fill=True,
    fill_opacity=0.1
).add_to(m)

# Marqueurs des villes
for _, row in communes_filtrees.iterrows():
    color = "green" if row["nom"] in st.session_state.selected_villes else "red"
    folium.Marker(
        location=[row["latitude"], row["longitude"]],
        popup=row["nom"],
        icon=folium.Icon(color=color)
    ).add_to(m)

# Interaction carte
map_data = st_folium(m, height=500, width=700)

# Gestion des clics
if map_data and map_data["last_object_clicked_popup"]:
    ville_cliquee = map_data["last_object_clicked_popup"]
    if ville_cliquee in st.session_state.selected_villes:
        st.session_state.selected_villes.remove(ville_cliquee)
    else:
        st.session_state.selected_villes.append(ville_cliquee)

# Filtrer les villes finales
final_villes = communes_filtrees[communes_filtrees["nom"].isin(st.session_state.selected_villes)]

# Tableau résultats
st.subheader("Résultats")
st.dataframe(final_villes[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

# Codes postaux à copier
codes_postaux = final_villes["code_postal"].tolist()
resultat_texte = ", ".join(codes_postaux)
st.text_area("Zone de chalandise :", resultat_texte, height=100)
