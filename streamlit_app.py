import streamlit as st
from openai import OpenAI
import base64
import requests

# --- API Keys ---
GOOGLE_VISION_API_KEY = st.secrets["google_api_key"]
OPENAI_API_KEY = st.secrets["openai_api_key"]
client = OpenAI(api_key=OPENAI_API_KEY) 


# --- Styled Logo Header ---
st.markdown(
    "<h1 style='font-family: Poppins, sans-serif; color: rgb(37,36,131); font-size: 2.5rem;'>AdaptTable</h1>",
    unsafe_allow_html=True
)

# --- Welcome Message ---
st.markdown("""
#### 👋 Welcome to AdaptTable – your household health co-pilot.

I’m here to help you meet your family’s health goals through smarter, easier food choices.

To get started, I’ll take a look at your recent grocery receipts. This helps me understand your household’s food habits so I can tailor guidance to your family’s needs.
""")


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

    # Debug output (shows raw Vision API result, even on failure)
    st.write("🧪 Vision API raw response:")



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

     
            # --- ChatGPT Prompt: Item Extraction & Formatting ---
            st.subheader("Generating Master Shopping Record...")
            
            prompt = f"""
            SYSTEM PROMPT: Receipt Item Extraction & Formatting  
            Task:  
            Extract and format all items from a grocery receipt processed through OCR (Optical Character Recognition) for inclusion in a master shopping record. This record will support later analysis of dietary habits, food preferences, and household size.
            
            Instructions:
            1. Data Review:
            - Review all extracted receipt content carefully.  
            - Do not remove any items, including non-food or miscellaneous products.  
            - Do not infer, hallucinate, or fabricate missing or unclear items.  
            - Do not consolidate duplicates — list each item exactly as it appears and in the order it was found.
            
            2. Output Formatting:
            - Store Name: As printed on the receipt  
            - Date: As printed on the receipt  
            - Items:
              - Present as a numbered list, maintaining original order  
              - For each item, preserve original wording.  
              - Only add an expanded version when the abbreviation is clearly and confidently known.
            
            3. Abbreviation Expansion Rules:
            - Expand abbreviations only if you are highly confident of the full name (e.g., “GV Shpsh” → “Great Value Sharp Shredded Cheddar”).  
            - If you are not sure, leave the original abbreviation untouched.  
            - Use → to show expansions or corrections (e.g., GV Shpsh → Great Value Sharp Shredded Cheddar).
            
            4. OCR Correction Guidelines:
            - Correct only clear OCR typos (e.g., “Chedar” → “Cheddar”)  
            - Do not interpret categories or food types — preserve the item’s literal content.  
            - Prioritize data integrity over clarity. When unsure, keep the original.
            
            Return only the structured output in this format. Do not add explanations, notes, or commentary.
            
            Extracted Receipt Text:
            {text}
            """
            
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}]
            )
            
            cleaned_items_output = response.choices[0].message.content
            st.markdown("### 🧾 Master Shopping Record:")
            st.markdown(cleaned_items_output)


        else:
            st.error("No text detected. Please try another image or ensure the receipt is well-lit and readable.")

    except Exception as e:
        st.error("There was a problem extracting text or generating the shopping record.")
        st.exception(e)
