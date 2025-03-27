import streamlit as st
import openai
import base64
import requests

# --- API Keys ---
GOOGLE_VISION_API_KEY = st.secrets["google_api_key"]
OPENAI_API_KEY = st.secrets["openai_api_key"]
openai.api_key = OPENAI_API_KEY

# --- App Title ---
st.title("🧾 adaptTable Receipt Analyzer")

# --- File Upload ---
uploaded_file = st.file_uploader("Upload your grocery receipt image", type=["jpg", "jpeg", "png"])

if uploaded_file:
    image_content = uploaded_file.read()
    image_base64 = base64.b64encode(image_content).decode("utf-8")

    # --- Google Vision OCR ---
    st.subheader("Extracting text from your receipt...")
    vision_url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
    vision_payload = {
        "requests": [{
            "image": {"content": image_base64},
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }

    vision_response = requests.post(vision_url, json=vision_payload)
    result = vision_response.json()
    
   try:
    if (
        isinstance(result, dict) and
        "responses" in result and
        isinstance(result["responses"], list) and
        len(result["responses"]) > 0 and
        "fullTextAnnotation" in result["responses"][0]
    ):
        text = result["responses"][0]["fullTextAnnotation"]["text"]
        st.text_area("📝 Raw Extracted Text", text, height=200)

        # --- ChatGPT Prompt ---
        st.subheader("Generating Pen Portrait...")
        prompt = f"""
        You are a food data analyst for a nutrition startup. A user has uploaded a receipt containing the following grocery items:

        {text}

        Clean this data (no hallucinations or assumptions). Then, generate a short Pen Portrait describing what this household likely eats, buys, and prefers based on the receipt.
        """

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        pen_portrait = response['choices'][0]['message']['content']
        st.markdown("### 🪞 Your Household's Pen Portrait:")
        st.markdown(pen_portrait)

    else:
        st.error("No text detected. Please try another image or ensure the receipt is well-lit and readable.")

except Exception as e:
    st.error("There was a problem extracting text or generating the Pen Portrait.")
    st.exception(e)

        # --- ChatGPT Prompt ---
        st.subheader("Generating Pen Portrait...")
        prompt = f"""
        You are a food data analyst for a nutrition startup. A user has uploaded a receipt containing the following grocery items:

        {text}

        Clean this data (no hallucinations or assumptions). Then, generate a short Pen Portrait describing what this household likely eats, buys, and prefers based on the receipt.
        """

        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )

        pen_portrait = response['choices'][0]['message']['content']
        st.markdown("### 🪞 Your Household's Pen Portrait:")
        st.markdown(pen_portrait)

    except Exception as e:
        st.error("There was a problem extracting text or generating the Pen Portrait.")
        st.exception(e)
