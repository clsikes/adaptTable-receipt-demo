import streamlit as st
from openai import OpenAI
import base64
import requests
import streamlit.components.v1 as components




# --- API Keys ---
GOOGLE_VISION_API_KEY = st.secrets["google_api_key"]
OPENAI_API_KEY = st.secrets["openai_api_key"]
client = OpenAI(api_key=OPENAI_API_KEY)

# --- Helper Function: Extract all store blocks from markdown table ---
def extract_all_store_blocks(parsed_text):
    blocks = []
    current_store = None
    current_items = []

    for line in parsed_text.strip().splitlines():
        line = line.strip()
        if line.lower().startswith("store name:"):
            if current_store and current_items:
                blocks.append((current_store, "\n".join(current_items)))
                current_items = []
            current_store = line.split(":", 1)[-1].strip()

        elif line.startswith("| Raw Item"):
            continue  # skip header
        elif line.startswith("|") and current_store:
            parts = line.split("|")
            if len(parts) > 2:
                raw = parts[1].strip()
                if raw.lower() != "raw item":
                    current_items.append(raw)
        elif not line and current_store and current_items:
            blocks.append((current_store, "\n".join(current_items)))
            current_store = None
            current_items = []

    # Catch final block
    if current_store and current_items:
        blocks.append((current_store, "\n".join(current_items)))

    return blocks


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

# --- Role-Based Access (Hybrid: URL + Password) ---
from urllib.parse import parse_qs

query_params = st.query_params
user_role = query_params.get("role", "patient")

# Optional Enhancement
if "last_user_role" in st.session_state and st.session_state.last_user_role != user_role:
    st.session_state.uploaded_receipts = []
st.session_state.last_user_role = user_role

st.markdown(f"🔍 **Current user role detected:** `{user_role}`")


if user_role == "provider":
    password = st.text_input("Enter provider access code:", type="password")
    if password != "rdn2024":
        st.warning("Access denied. Please enter the correct provider code.")
        st.stop()

# --- Session State for Multi-Upload ---
if "uploaded_receipts" not in st.session_state:
    st.session_state.uploaded_receipts = []

# --- Upload UI ---
new_receipt = st.file_uploader("Upload your grocery receipt image", type=["jpg", "jpeg", "png"])

if new_receipt is not None:
    if new_receipt.name not in [f.name for f in st.session_state.uploaded_receipts]:
        st.session_state.uploaded_receipts.append(new_receipt)
        st.success("Receipt uploaded!")
    else:
        st.warning("This receipt has already been uploaded.")

# --- Show Receipt Count ---
if st.session_state.uploaded_receipts:
    st.markdown(f"📥 **{len(st.session_state.uploaded_receipts)} receipt(s) uploaded:**")
    for file in st.session_state.uploaded_receipts:
        st.markdown(f"- {file.name}")

    # --- Conversational Prompt ---
    st.markdown("**I’ve scanned and structured your shopping data.**")
    
    st.markdown("""
    Would you like to upload more receipts so I can get the full picture of your household's food habits?
    
    You can use the upload box above to add more receipts.
    """)
    
    proceed = st.button("✅ I'm Ready – Analyze My Shopping Data")


else:
    proceed = False


# --- Combined Text Extraction and Analysis ---
if proceed:
    combined_text = ""

    for uploaded_file in st.session_state.uploaded_receipts:
        uploaded_file.seek(0)  # ✅ Reset file pointer
        image_content = uploaded_file.read()
        image_base64 = base64.b64encode(image_content).decode("utf-8")

        vision_url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
        vision_payload = {
            "requests": [{
                "image": {"content": image_base64},
                "features": [{"type": "TEXT_DETECTION"}]
            }]
        }

        vision_response = requests.post(vision_url, json=vision_payload)
        result = vision_response.json()

        if (
            isinstance(result, dict) and
            "responses" in result and
            isinstance(result["responses"], list) and
            len(result["responses"]) > 0 and
            "fullTextAnnotation" in result["responses"][0]
        ):
            extracted_text = result["responses"][0]["fullTextAnnotation"]["text"]
            combined_text += extracted_text + "\n\n"
        else:
            st.error(f"Could not process: {uploaded_file.name}. Please check image quality.")
            st.stop()

    # --- Show All Raw Combined Text ---
    st.text_area("📝 Combined Receipt Text", combined_text, height=250)

    with st.spinner("⏳ Analyzing your grocery receipts... This may take 20–30 seconds."):
        try:
            st.subheader("Generating Master Shopping Record...")

            system_prompt_receipt_parser = """

            You are an expert receipt parser. Your role is to extract and expand grocery items from OCR-processed receipts using consistent formatting and practical product knowledge.

            You will be provided with:
            - The name of the store (e.g., Walmart)
            - A full list of extracted receipt text
            
            Your job:
            - Extract the raw item names exactly as written
            - Use your knowledge of common grocery products, retail item formats, and the store context to expand abbreviated names
            
            ### Output Format
            Return your output as a markdown table with two columns:
            | Raw Item | Expansion |
            
            Formatting Rules:
            - List every item in order. Include the original item name as-is under “Raw Item.”
            - Use the “Expansion” column to rewrite the full product name if you can confidently infer it from:
              - Common abbreviations (e.g., “GV SHP SH” → “Great Value Sharp Shredded Cheddar”)
              - Known store-brand items (e.g., Walmart’s Great Value)
              - Household or grocery items (e.g., “POPCRN” → “Popcorn”, “HP JUICE” → “High Pulp Juice”)
              - Product codes or sizes when common (e.g., “1.62Z KA LIQ” → “1.62 oz Kool-Aid Liquid”)
            - If the item is unclear or unknown, mark the Expansion as `Ambiguous`
            
            Do not:
            - Skip items
            - Remove duplicates
            - Guess fictional products
            - Reorganize or reclassify
            - Add a third column or commentary
            
            If the receipt includes a store name, use it to inform what types of products are likely to appear.
            
            You may expand even without 100% certainty when:
            - The expansion is widely accepted/common at that store
            - The abbreviation closely matches a well-known grocery item
            - The context is strong enough (e.g., surrounded by other dairy items)


            """


            user_prompt_receipt_parser = f"""
          
            Extract the store name, date, and all receipt items from the text below. 
            Follow the format:
            
            Store Name: [Store Name]  
            Date: [Date]  
            
            | Raw Item | Expansion |
            |----------|-----------|
            | ITEM A   | Expansion |
            | ITEM B   | Ambiguous |
            
            Extracted Receipt Text:
            {combined_text}
            """

    

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt_receipt_parser},
                    {"role": "user", "content": user_prompt_receipt_parser}
                ]
            )

            cleaned_items_output = response.choices[0].message.content
            st.markdown("### 🧾 Your Master Shopping Record")

            components.html(
                f"""
                <div style="max-height: 300px; overflow-y: auto; padding: 10px; border: 1px solid #ccc; border-radius: 8px;">
                    <pre style="white-space: pre-wrap;">{cleaned_items_output}</pre>
                </div>
                """,
                height=350,
                scrolling=True
            )
            

            # --- Extract Raw Items Only (for LLM use) ---
            store_blocks = extract_all_store_blocks(cleaned_items_output)
    
            combined_raw_items = "\n\n".join(
                f"**Store: {store}**\n{items}" for store, items in store_blocks
            )
    
           

        except Exception as e:
            st.error("There was a problem generating the shopping record.")
            st.exception(e)

    try:
        st.subheader("🩺 Household Behavior Profile")

        # --- Step 3: Generate Role-Based RDN Summary ---
  
        if user_role == "provider":
        pen_portrait_prompt = f"""
        You are an analytical and evidence-based Registered Dietitian Nutritionist (RDN) working in an endocrinology clinic. You have just received a Master Shop Record containing a list of raw grocery receipt items, with optional expanded names.
    
        Your job is to create a clear, structured evaluation of this household's dietary habits. This is for internal use only and will inform how to tailor patient education and support — it will not be seen by the patient. Be precise and direct. Do not speculate or assign blame.
    
        Instructions:
        - Use the Raw Item names as your primary reference.
        - You may reference the Expansion column **only when it improves clarity or supports stronger dietary insight**.
        - Avoid using the Expansion if the item is marked Ambiguous.
        - Focus on dietary patterns, macronutrient quality, and clinical implications for diabetes or glycemic control.
        - Do not categorize items or infer food groups — instead, infer patterns based on known food items.
        - Avoid overgeneralizing from isolated purchases.
    
        Your output should include:
    
        ### Clinical Assessment Summary:
        (A brief, direct analysis of food behaviors and clinical considerations)
    
        ### Key Dietary Insights:
        - Bullet 1
        - Bullet 2
        - Bullet 3
    
        Master Shop Record:
        {cleaned_items_output}
        """
        system_message = "You are a clinical RDN. Base your assessment primarily on Raw Item names, using Expansion only when it increases clarity and is not marked Ambiguous."
    
    else:
        pen_portrait_prompt = f"""
        You are an empathetic, evidence-based Registered Dietitian Nutritionist (RDN) specializing in Diabetes. You’ve just received a Master Shop Record of grocery items — it includes a column of raw item names and optional expanded names.
    
        Your job is to write a short, clear narrative summary that describes this household's grocery habits and food patterns. This summary will be seen by the patient, so it should be easy to understand and reflect their shopping patterns accurately.
    
        Objective: Build trust and show that the user's food choices are understood, before providing any behavior change guidance.
    
        Instructions:
        - Base your summary primarily on the Raw Item names in the Master Shop Record.
        - You may use the Expansion column **only if it makes the item clearer and it is not marked Ambiguous**.
        - Focus on consistent patterns, not isolated items.
        - Avoid making dietary category guesses unless strongly supported.
        - Keep the tone clear, observational, and specific — not vague or overly flattering.
    
        Output should include:
    
        ### Narrative Household Profile:
        (3–5 sentence descriptive summary that reflects the household and food patterns)
    
        ### Notable Shopping Trends:
        - Bullet 1
        - Bullet 2
        - Bullet 3
    
        Master Shop Record:
        {cleaned_items_output}
        """
        system_message = "You are an empathetic RDN. Base insights on Raw Item names, using the Expansion column only when it provides clear, helpful detail and is not marked Ambiguous."
      
        pen_portrait_response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": pen_portrait_prompt}
            ]
        )

        pen_portrait_output = pen_portrait_response.choices[0].message.content

              # Final Output
       
  
        st.subheader("💡 Summary of Your Shopping Habits" if user_role == "patient" else "🩺 Final Household Summary")
        st.markdown(pen_portrait_output)



    except Exception as e:
        st.error("There was a problem generating the Household Profile.")
        st.exception(e)

        
