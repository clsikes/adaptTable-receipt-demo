import streamlit as st
from openai import OpenAI
import base64
import requests
import streamlit.components.v1 as components
import os
import toml
import time
import google.generativeai as genai

# Add custom CSS for food items
st.markdown("""
<style>
.food-item-helpful {
    background-color: #e8f5e9;  /* Light green background */
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
    font-size: 1.2em;
    font-weight: 600;
    color: #2e7d32;  /* Darker green text */
}
.food-item-challenging {
    background-color: #ffebee;  /* Light red background */
    padding: 15px;
    border-radius: 8px;
    margin: 15px 0;
    font-size: 1.2em;
    font-weight: 600;
    color: #c62828;  /* Darker red text */
}
</style>
""", unsafe_allow_html=True)

# --- Callback Function ---
def on_continue_click():
    st.session_state.analysis_complete = True
    st.session_state.show_helps_hinders = True

def on_radio_change():
    # This function will be called when the radio button changes
    # It doesn't need to do anything, just being called prevents the page reload
    pass

def on_continue_to_guidance_click():
    st.session_state.analysis_complete = True
    st.session_state.show_helps_hinders = True
    # Clear any existing helps/hinders content to ensure fresh generation
    if 'helpful_foods_content' in st.session_state:
        del st.session_state.helpful_foods_content
    if 'challenging_foods_content' in st.session_state:
        del st.session_state.challenging_foods_content

# --- Load Secrets ---
try:
    # Try to load from Streamlit Cloud secrets first
    GOOGLE_VISION_API_KEY = st.secrets["google_api_key"]
    OPENAI_API_KEY = st.secrets["openai_api_key"]
    GOOGLE_AI_API_KEY = st.secrets["google_ai_api_key"]  # Add this for Gemini
except Exception as e:
    st.error("Error loading secrets from Streamlit Cloud. Please ensure all API keys are configured in your Streamlit Cloud secrets.")
    st.stop()

# Initialize clients
client = OpenAI(api_key=OPENAI_API_KEY)
genai.configure(api_key=GOOGLE_AI_API_KEY)

# --- Initialize Session State ---
if "uploaded_receipts" not in st.session_state:
    st.session_state.uploaded_receipts = []
if "show_helps_hinders" not in st.session_state:
    st.session_state.show_helps_hinders = False
if "master_record" not in st.session_state:
    st.session_state.master_record = None
if "household_summary" not in st.session_state:
    st.session_state.household_summary = None
if "analysis_complete" not in st.session_state:
    st.session_state.analysis_complete = False
if "cleaned_items_output" not in st.session_state:
    st.session_state.cleaned_items_output = None
if "current_step" not in st.session_state:
    st.session_state.current_step = "upload"
if "processing_times" not in st.session_state:
    st.session_state.processing_times = {}

# --- Model Selection ---
st.sidebar.title("Model Selection")
model_choice = st.sidebar.selectbox(
    "Select Model",
    ["OpenAI GPT-4o", "OpenAI GPT-3.5-Turbo-0125", "Google Gemini 2.5"],
    index=0
)

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
            blocks.append((current_store, current_items))
            current_store = None
            current_items = []

    # Catch final block
    if current_store and current_items:
        blocks.append((current_store, current_items))

    return blocks

# --- Styled Logo Header ---
st.markdown(
    "<h1 style='font-family: Poppins, sans-serif; color: rgb(37,36,131); font-size: 2.5rem;'>AdaptTable</h1>",
    unsafe_allow_html=True
)

# --- Welcome Message ---
st.markdown("""
### 👋 Welcome to AdaptTable – your household health co-pilot

Learning how to use food to help manage a health condition—or simply eat better—can feel overwhelming:
- 🤔 *How am I doing with my current diet?*  
- 🔄 *What exactly needs to change?*  
- 👨‍👩‍👧 *How do I make changes that my whole household will actually accept?*

I'm here to make improving your household's health through food easier, more achievable, and more acceptable - for everyone in the family  (yes, even you—Seafood-Skeptic-of-the-Deep 🐟🙅‍♂️).

We'll start by analyzing your most recent grocery receipts to spot habits that might help—or hinder—your health goals.  
From there, I'll offer realistic food swaps and tailor shopping, meal plans, and cooking strategies for your household's specific needs.

📸 **Let's get started!**  
Snap a photo of your grocery receipt—make sure the store name is visible.  
Upload as many as you like (the more items, the better)!
""")

# --- Upload UI ---
st.markdown("### 📤 Upload Your Receipt")
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
    st.markdown("**I've scanned and structured your shopping data.**")
    
    st.markdown("""
    Would you like to upload more receipts so I can get the full picture of your household's food habits?
    
    You can use the upload box above to add more receipts.
    """)
    
    proceed = st.button("✅ I'm Ready – Analyze My Shopping Data")
    if proceed:
        st.session_state.current_step = "analysis"
else:
    proceed = False

# --- Combined Text Extraction and Analysis ---
if st.session_state.current_step == "analysis":
    combined_text = ""

    for uploaded_file in st.session_state.uploaded_receipts:
        uploaded_file.seek(0)  # Reset file pointer
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

    with st.spinner(f"⏳ Analyzing your grocery receipts with {model_choice}... This may take 20–30 seconds."):
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
            - List every item in order. Include the original item name as-is under "Raw Item."
            - Use the "Expansion" column to rewrite the full product name if you can confidently infer it from:
              - Common abbreviations (e.g., "GV SHP SH" → "Great Value Sharp Shredded Cheddar")
              - Known store-brand items (e.g., Walmart's Great Value)
              - Household or grocery items (e.g., "POPCRN" → "Popcorn", "HP JUICE" → "High Pulp Juice")
              - Product codes or sizes when common (e.g., "1.62Z KA LIQ" → "1.62 oz Kool-Aid Liquid")
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

            # Process with selected model
            start_time = time.time()
            
            if model_choice == "OpenAI GPT-4o":
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_prompt_receipt_parser},
                        {"role": "user", "content": user_prompt_receipt_parser}
                    ]
                )
                cleaned_items_output = response.choices[0].message.content
            elif model_choice == "OpenAI GPT-3.5-Turbo-0125":
                response = client.chat.completions.create(
                    model="gpt-3.5-turbo-0125",
                    messages=[
                        {"role": "system", "content": system_prompt_receipt_parser},
                        {"role": "user", "content": user_prompt_receipt_parser}
                    ]
                )
                cleaned_items_output = response.choices[0].message.content
            elif model_choice == "Google Gemini 2.5":
                model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
                response = model.generate_content(
                    f"{system_prompt_receipt_parser}\n\n{user_prompt_receipt_parser}"
                )
                cleaned_items_output = response.text
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Store the processing time
            if "receipt_parsing" not in st.session_state.processing_times:
                st.session_state.processing_times["receipt_parsing"] = {}
            
            st.session_state.processing_times["receipt_parsing"][model_choice] = processing_time
            
            st.session_state.master_record = cleaned_items_output
            st.session_state.cleaned_items_output = cleaned_items_output
            
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
            
            # Display processing time
            st.info(f"Processing time: {processing_time:.2f} seconds")

            # --- Extract Raw Items Only (for LLM use) ---
            store_blocks = extract_all_store_blocks(cleaned_items_output)
            combined_raw_items = "\n\n".join(
                f"**Store: {store}**\n{items}" for store, items in store_blocks
            )

            # Set analysis_complete to True after generating the master record
            st.session_state.analysis_complete = True

        except Exception as e:
            st.error("There was a problem generating the shopping record.")
            st.exception(e)

    try:
        st.subheader("💡 Summary of Your Shopping Habits")

        # Only generate summary if it doesn't exist in session state or is None
        if 'household_summary' not in st.session_state or st.session_state.household_summary is None:
            pen_portrait_prompt = f"""
            You are a registered dietitian who specializes in empowering households to understand and improve their food choices. You are reviewing the output of a tool that converts a grocery receipt into a structured list of items. Each item may include a short name and, when possible, a longer expansion. You are creating a patient-facing summary to help the user understand their shopping habits and identify opportunities for improvement. The tone should be supportive but not overly positive — focus on clear, specific insights rooted in evidence and behavioral observation.
            
            Step 1: Review Input Format
            You are provided with a list of grocery items purchased by a household. Each row contains a raw item name and, when available, a confident expansion. Use both fields when identifying trends, favoring the expansion when it offers more clarity. Do not make assumptions based on items that are unclear or ambiguous.
            
            Step 2: Identify and Analyze Shopping Patterns
            Analyze shopping patterns based solely on the visible item names and expansions. Do not rely on any internal food database. Instead, use commonsense knowledge and observable trends. Where appropriate, cite examples from the list. Analyze for the following:
            
            - ✅ Recurring food categories, such as proteins, grains, snacks, dairy, beverages, sweets, condiments, or frozen meals. Name the categories only if there are multiple examples.
            - ✅ Household size & composition, if inferable (e.g., kids, adults, multiple dietary needs).
            - ✅ Meal preparation habits, such as reliance on convenience items vs. ingredients for home-cooked meals.
            - ✅ Spending habits, such as bulk items, store brands, or premium brands.
            - ✅ Dietary preferences or restrictions, such as gluten-free, low-carb, vegetarian, etc.
            - ✅ Brand preferences, if certain brands appear multiple times.
            - ✅ Lifestyle indicators, such as a busy or social household — include only if confident based on 3+ distinct items (≥60% confidence).
            - ✅ Unexpected or culturally specific patterns, like repeated purchases of a specific spice, dish, or ingredient type.
            
            Cite only patterns that are clearly supported by the data. Avoid vague or overly positive generalizations.
            
            Step 3: Write the Patient Summary
            Write a short, specific summary that reflects this household's current shopping patterns. Use an empathetic tone, but prioritize clarity, usefulness, and behavioral insight. If relevant, comment on strengths and possible areas for improvement in a way that helps the household feel understood and supported. Do not mention any item that wasn't clearly extracted or expanded.
            
            Master Shop Record:
            {cleaned_items_output}
            """
            system_message = "You are a registered dietitian. Base your summary on Raw Item names, using Expansion only when it improves clarity. Do not use expansions marked Ambiguous."

            # Process with selected model
            start_time = time.time()
            
            if model_choice == "OpenAI GPT-4o":
                pen_portrait_response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": pen_portrait_prompt}
                    ]
                )
                pen_portrait_output = pen_portrait_response.choices[0].message.content
            elif model_choice == "OpenAI GPT-3.5-Turbo-0125":
                pen_portrait_response = client.chat.completions.create(
                    model="gpt-3.5-turbo-0125",
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": pen_portrait_prompt}
                    ]
                )
                pen_portrait_output = pen_portrait_response.choices[0].message.content
            elif model_choice == "Google Gemini 2.5":
                model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
                response = model.generate_content(
                    f"{system_message}\n\n{pen_portrait_prompt}"
                )
                pen_portrait_output = response.text
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            # Store the processing time
            if "household_summary" not in st.session_state.processing_times:
                st.session_state.processing_times["household_summary"] = {}
            
            st.session_state.processing_times["household_summary"][model_choice] = processing_time
            
            # Store the summary in session state if it's not None or empty
            if pen_portrait_output and pen_portrait_output.strip():
                st.session_state.household_summary = pen_portrait_output
            else:
                st.error("Failed to generate household summary. Please try again.")
                st.stop()

        # Display the stored summary if it exists and is not None
        if st.session_state.household_summary and st.session_state.household_summary.strip():
            st.markdown(st.session_state.household_summary)
            
            # Display processing time if available
            if "household_summary" in st.session_state.processing_times and model_choice in st.session_state.processing_times["household_summary"]:
                st.info(f"Processing time: {st.session_state.processing_times['household_summary'][model_choice]:.2f} seconds")

            # Add a message about the summary
            st.info("The things in our shopping carts can tell us a lot about a household, but not everything. If this doesn't sound like you don't worry - we will get detailed information about your HH at a later step.")
            
            # Show continue button only if we have a valid summary
            st.button("Continue to Food Guidance", on_click=on_continue_to_guidance_click)
        else:
            st.error("No valid household summary available. Please try again.")
            st.stop()

    except Exception as e:
        st.error("There was a problem generating the Household Profile.")
        st.exception(e)

# --- Helps / Hinders GPT Analysis Block ---
if st.session_state.analysis_complete and st.session_state.show_helps_hinders and st.session_state.master_record:
    st.subheader("🍽️ How Your Foods May Impact Blood Sugar")
    try:
        # Define the helpful foods prompt
        helpful_foods_prompt = f"""
        🧠 ROLE:
        You are a registered dietitian helping a household understand how their recent grocery purchases may affect blood sugar control for someone managing Type 1 Diabetes (T1D).

        🎯 GOAL:
        From the Master Shopping Record, analyze the food items and produce friendly, fact-based, actionable guidance grounded in nutritional science that:
        - Helps users understand which foods support or challenge blood sugar control
        - Explains *why* in clear, evidence-based language
        - Provides alternatives and practical adaptation tips
        - Supports decision-making for future shops or conversations with health care providers

        Only use food items that appear in the provided shopping list — never invent or assume new ones.

        ---

        STEP 1: Write a Conversational Introduction
        Start with a friendly, personalized introduction that:
        - Acknowledges their shopping choices
        - Sets up the purpose of the analysis
        - Creates a supportive, non-judgmental tone
        Example: "I've reviewed your recent shopping list, and I'm excited to help you understand how these choices might affect your blood sugar control. Let's look at specific items that could help support your goals..."

        STEP 2: Analyze Helpful Foods
        For each food that supports blood sugar control (low-GI, high-fiber, high-protein, or rich in healthy fats):
        - Identify all relevant items from their shopping list
        - Use appropriate food icons (🥑 for avocado, 🥛 for milk, 🥬 for vegetables, etc.)
        - Format each item EXACTLY as follows with double line breaks between items:
          **🥑 Food Item:** [name]  
          
          **✅ Why It's Great for Blood Sugar Control:** [clear, evidence-based explanation]  
          
          **🍽️ How to Use It:** [practical, specific suggestions]
          
          [Double line break before next item]

        ✅ RULES:
        - Never make up food items
        - Do not give medical advice or suggest medication
        - Use a friendly, informative tone that builds confidence
        - Keep explanations evidence-based and specific
        - Use appropriate food icons that match the items
        - Analyze ALL relevant items from the shopping list
        - Do not show the steps or internal structure to the user
        - IMPORTANT: Use double line breaks between each food item to ensure proper formatting

        Master Shop Record:
        {st.session_state.master_record}
        """

        # Process helpful foods first if not already in session state
        if 'helpful_foods_content' not in st.session_state:
            with st.spinner("Analyzing helpful foods in your shopping list..."):
                start_time = time.time()
                
                if model_choice == "OpenAI GPT-4o":
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "You are a registered dietitian specializing in diabetes management."},
                            {"role": "user", "content": helpful_foods_prompt}
                        ]
                    )
                    helpful_foods_output = response.choices[0].message.content
                elif model_choice == "OpenAI GPT-3.5-Turbo-0125":
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo-0125",
                        messages=[
                            {"role": "system", "content": "You are a registered dietitian specializing in diabetes management."},
                            {"role": "user", "content": helpful_foods_prompt}
                        ]
                    )
                    helpful_foods_output = response.choices[0].message.content
                elif model_choice == "Google Gemini 2.5":
                    model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
                    response = model.generate_content(
                        f"You are a registered dietitian specializing in diabetes management.\n\n{helpful_foods_prompt}"
                    )
                    helpful_foods_output = response.text
                
                end_time = time.time()
                helpful_processing_time = end_time - start_time
                
                # Store in session state
                st.session_state.helpful_foods_content = helpful_foods_output
                st.session_state.helpful_processing_time = helpful_processing_time

        # Display helpful foods
        if 'helpful_foods_content' in st.session_state:
            content_parts = st.session_state.helpful_foods_content.split("\n\n")
            if content_parts:
                intro = content_parts[0]
                st.markdown(intro)
                st.markdown("<h3 style='font-size: 1.5rem; font-weight: 600; color: #2e7d32; margin-top: 1.5em; margin-bottom: 1em;'>Here are some items from your list that can be particularly helpful in managing blood sugar:</h3>", unsafe_allow_html=True)
                
                for part in content_parts[1:]:
                    if "Food Item:" in part:
                        lines = part.split("\n")
                        food_line = next(line for line in lines if "Food Item:" in line)
                        # Make food items larger and bolder
                        modified_part = part.replace(food_line, f'<div style="font-size: 1.2em; font-weight: 600; margin: 1em 0;">{food_line}</div>')
                        st.markdown(modified_part, unsafe_allow_html=True)
                    else:
                        st.markdown(part)
        
            st.info(f"Helpful foods analysis completed in {st.session_state.helpful_processing_time:.2f} seconds")

        # Process challenging foods in background if not already done
        if 'challenging_foods_content' not in st.session_state:
            challenging_foods_prompt = f"""
            🧠 ROLE:
            You are a registered dietitian helping a household understand how their recent grocery purchases may affect blood sugar control for someone managing Type 1 Diabetes (T1D).

            🎯 GOAL:
            From the Master Shopping Record, analyze the food items and produce friendly, fact-based, actionable guidance grounded in nutritional science that:
            - Helps users understand which foods support or challenge blood sugar control
            - Explains *why* in clear, evidence-based language
            - Provides alternatives and practical adaptation tips
            - Supports decision-making for future shops or conversations with health care providers

            Only use food items that appear in the provided shopping list — never invent or assume new ones.

            ---

            STEP 1: Analyze Challenging Foods
            For each food that may hinder blood sugar control (high-GI, refined carbs, low fiber, low protein, or high in added sugar):
            - Identify all relevant items from their shopping list
            - Use appropriate food icons (🍞 for bread, 🍪 for cookies, 🥤 for sugary drinks, etc.)
            - Format each item EXACTLY as follows with double line breaks between items:
              **[icon] Food Item:** [name]  
              
              **❌ Why It May Challenge Control:** [clear, evidence-based explanation]  
              
              **✅ Try Instead:** [specific alternative with better glycemic profile]  
              
              **🔄 Adaptation Tip:** Suggest how to still use or enjoy this food with adjustments (e.g., pairing with protein, changing timing, reducing portion)
              
              [Double line break before next item]

            STEP 2: Include Fixed Top Tips Section
            Always include these specific tips, personalizing only the bracketed examples with items from their shopping list:

            💡 **Top Tips for Blood Sugar Stability**

            **🥚 Savory Breakfast First**  
            Most people love a sweet start like [insert item if available – e.g., bananas or honey]. But mornings are when your body is more insulin-resistant — so starting with sugary foods can lead to big blood sugar spikes. Have some protein or fat first (e.g., turkey sausage, egg, avocado) to slow down absorption.

            **🥦 Eat Veggies First**  
            If your meals include pasta, rice, or bread, eat veggies or salad first. The fiber acts like a barrier and slows down carb absorption — making blood sugar easier to manage.

            **🍽️ Eat In This Order:**  
            Veggies → Protein/Fat → Carbs  
            This simple order change can dramatically reduce blood sugar spikes.

            **🧬 Pair Your Carbs**  
            Got bread, granola bars, or crackers? Pair them with nut butter, cheese, or Greek yogurt. The added fat and protein help slow digestion.

            **👟 Move After Meals**  
            Even 10 minutes of walking after a meal can help flatten your glucose curve and aid digestion.

            **🍏 Juice = Medicine, Not a Drink**  
            Juice like [insert juice brand if available] works great for treating low blood sugar — but not for sipping throughout the day. Try water with lemon or a splash of juice instead.

            **🥖 Choose Whole Over Processed**  
            Highly processed foods (like [insert example from cart]) spike blood sugar faster. Opt for whole, fiber-rich versions when you can.

            **🌾 Fiber = Power**  
            Fiber slows digestion and supports blood sugar balance. Beans, whole grains, lentils, veggies — aim for more!

            **🧘‍♀️ Sleep & Stress Matter**  
            Poor sleep and stress can raise blood sugar. Prioritize rest and find calming rituals like yoga, walking, or mindfulness.

            ✅ RULES:
            - Never make up food items
            - Do not give medical advice or suggest medication
            - Use a friendly, informative tone that builds confidence
            - Keep explanations evidence-based and specific
            - Use appropriate food icons that match the items
            - Analyze ALL relevant items from the shopping list
            - Do not show the steps or internal structure to the user
            - Maintain the exact wording of the top tips section, only personalizing the bracketed examples
            - IMPORTANT: Use double line breaks between each food item to ensure proper formatting

            Master Shop Record:
            {st.session_state.master_record}
            """

            with st.spinner("Analyzing challenging foods in your shopping list..."):
                start_time = time.time()
                
                if model_choice == "OpenAI GPT-4o":
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": "You are a registered dietitian specializing in diabetes management."},
                            {"role": "user", "content": challenging_foods_prompt}
                        ]
                    )
                    challenging_foods_output = response.choices[0].message.content
                elif model_choice == "OpenAI GPT-3.5-Turbo-0125":
                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo-0125",
                        messages=[
                            {"role": "system", "content": "You are a registered dietitian specializing in diabetes management."},
                            {"role": "user", "content": challenging_foods_prompt}
                        ]
                    )
                    challenging_foods_output = response.choices[0].message.content
                elif model_choice == "Google Gemini 2.5":
                    model = genai.GenerativeModel('gemini-2.5-pro-preview-03-25')
                    response = model.generate_content(
                        f"You are a registered dietitian specializing in diabetes management.\n\n{challenging_foods_prompt}"
                    )
                    challenging_foods_output = response.text
                
                end_time = time.time()
                challenging_processing_time = end_time - start_time
                
                # Store in session state
                st.session_state.challenging_foods_content = challenging_foods_output
                st.session_state.challenging_processing_time = challenging_processing_time

        # Display challenging foods if available
        if 'challenging_foods_content' in st.session_state:
            content_parts = st.session_state.challenging_foods_content.split("\n\n")
            st.markdown("<h3 style='font-size: 1.5rem; font-weight: 600; color: #c62828; margin-top: 1.5em; margin-bottom: 1em;'>Now let's take a look at food items that could be more challenging:</h3>", unsafe_allow_html=True)
            
            for part in content_parts:
                if "Food Item:" in part:
                    lines = part.split("\n")
                    food_line = next(line for line in lines if "Food Item:" in line)
                    # Make food items larger and bolder
                    modified_part = part.replace(food_line, f'<div style="font-size: 1.2em; font-weight: 600; margin: 1em 0;">{food_line}</div>')
                    st.markdown(modified_part, unsafe_allow_html=True)
                elif "💡 **Top Tips" in part:
                    st.markdown("<h3 style='font-size: 1.5rem; font-weight: 600; color: #1565c0; margin-top: 1.5em; margin-bottom: 1em;'>💡 Top Tips for Blood Sugar Stability</h3>", unsafe_allow_html=True)
                    st.markdown(part)
                elif not any(skip in part for skip in ["let's take a look", "Okay,", "Remember, this is about"]):
                    st.markdown(part)
            
            st.info(f"Challenging foods analysis completed in {st.session_state.challenging_processing_time:.2f} seconds")

    except Exception as e:
        st.error("There was a problem generating the food guidance.")
        st.exception(e)

# --- Performance Metrics ---
if st.session_state.processing_times:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Performance Metrics")
    for step, times in st.session_state.processing_times.items():
        st.sidebar.markdown(f"**{step.replace('_', ' ').title()}:**")
        for model, time_taken in times.items():
            st.sidebar.markdown(f"- {model}: {time_taken:.2f} seconds")
