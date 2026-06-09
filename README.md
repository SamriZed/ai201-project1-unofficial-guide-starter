# The Unofficial Guide — Project 1

> **How to use this template:**
> Complete each section *after* you've built and tested the corresponding part of your system.
> Do not write placeholder text — if a section isn't done yet, leave it blank and come back.
> Every section below is required for submission. One-liners will not receive full credit.

---

## Domain

<!-- What topic or category of knowledge does your system cover?
     Why is this knowledge valuable, and why is it hard to find through official channels?
     Example: "Student reviews of CS professors at [university] — useful because official
     course descriptions don't reflect teaching style, exam difficulty, or workload." -->

This knowledge is valuable because students need to quickly find classmates and study groups for specific courses to succeed academically, especially in difficult or fast-paced classes. It’s hard to find through official channels because universities only provide enrollment lists, course catalogs, and formal club directories—not real-time, course-specific communities like Discords, GroupMe chats, or informal study groups created by students.

---

## Document Sources

<!-- List every source you collected documents from.
     Be specific: include URLs, subreddit names, forum thread titles, or file names.
     Aim for variety — sources that together cover different subtopics or perspectives. -->

| # | Source | Type | URL or file path |
|---|--------|------|-----------------|
| 1 |  TopUniversities| 7 Types of US College Student Organization| https://www.topuniversities.com/blog/7-types-us-college-student-organization|
| 2 | Reddit | How to find study groups | https://www.reddit.com/r/college/comments/r53cbz/how_to_find_study_group/|
| 3 | UCLA |Student Organization |https://sa.ucla.edu/RCO/public/search?q=club |
| 4 | University of St. Thomas| Organization | https://tommielink.stthomas.edu/organizations|
| 5 | Centre Multi| Chemical Engineering at UST | https://www.centremulti.qc.ca/qc-news/chemical-engineering-at-ust-reddit-insights-and-discussions-1767647678 |
| 6 | University of Rochester| Collaborative Learning|https://www.rochester.edu/college/learningcenter/collaborative/study-groups.html |
| 7 | GitHub| Computer Science Crew | https://github.com/uvmcscrew |
| 8 | UVM Academic success centers | Student groups UVM| https://success.umn.edu/studygroups |
| 9 | University of Michigan-Dearborn | Professional student organizations | https://umdearborn.edu/cob/life-cob/professional-student-organizations|
| 10 | Texas A&M University | Course Descriptions | https://catalog.tamu.edu/undergraduate/course-descriptions/|


---

## Chunking Strategy

<!-- Describe your chunking approach with enough specificity that someone else could reproduce it.
     Include:
     - Chunk size (characters or tokens) and why that size fits your documents
     - Overlap size and why (or why not) you used overlap
     - Any preprocessing you did before chunking (e.g., stripping HTML, removing headers)
     - What your final chunk count was across all documents -->

**Chunk size:**
~400 whitespace-delimited tokens per chunk (target `TARGET_CHUNK_TOKENS = 400`), which sits inside the 300–500 token window from my planning doc. Measured across the corpus, chunks ran from 106 tokens (the trailing chunk of a short document) to 400 tokens, averaging ~372.

**Overlap:**
50 tokens of overlap between consecutive chunks (`CHUNK_OVERLAP_TOKENS = 50`), so the sliding window advances 350 tokens at a time. I used overlap so that a community/club description that lands near a chunk boundary still appears intact in at least one chunk, instead of being split in half.

**Preprocessing before chunking:**
Each document is cleaned in `clean_text()` (in `rag_ingest_and_chunk.py`) before chunking: HTML is stripped with a custom `HTMLParser` that drops `script`/`style`/`nav`/`footer`/`form` content, HTML entities are unescaped, boilerplate lines are removed (cookie banners, "sign in", "menu", and metadata lines like `Advisor:`, `Email:`, `Category:`), and whitespace is collapsed. Documents are loaded offline from `sources.txt`/`documents/` rather than scraped live, so the pipeline is reproducible.

**Why these choices fit your documents:**
My sources are student-organization directories, Reddit threads, study-group pages, and course descriptions. A ~400-token chunk is large enough to keep one organization's full description (name, purpose, meeting details, contact) together, while still being specific enough that retrieval doesn't pull in a whole page. The 50-token overlap cushions boundary cases without creating heavy duplication.

**Final chunk count:**
63 chunks across 9 ingested documents.

---

## Embedding Model

<!-- Name the embedding model you used and explain your choice.
     Then answer: if you were deploying this system for real users and cost wasn't a constraint,
     what tradeoffs would you weigh in choosing a different model?
     Consider: context length limits, multilingual support, accuracy on domain-specific text,
     latency, and local vs. API-hosted. -->

**Model used:**
I used all-MiniLM-L6-v2 through the sentence-transformers library. I picked it because it's small and fast, runs on my own laptop for free, and works well for the short English text that makes up most of my sources. The embeddings are normalized and stored in ChromaDB with cosine similarity, and each question pulls back the 5 closest chunks.

**Production tradeoff reflection:**
If I were building this for real users and cost wasn't an issue, I'd think about two things. First, this model only reads about the first 256 word-pieces of a chunk, but my chunks are around 400 tokens, so the longest ones get cut off before they're embedded — a model with a longer limit, or smaller chunks, would fix that. Second, a bigger or paid model like bge-large-en or OpenAI's embeddings would probably do a better job telling similar club and course names apart, which is where my Texas A&M question went wrong. I'd also consider a multilingual model if I wanted to support international students. The trade-off is that better accuracy usually means slower speed, bigger models, and paying for an API instead of running everything locally.

---

## Grounded Generation

<!-- Explain how your system enforces grounding — how does it prevent the LLM from answering
     beyond the retrieved documents?
     Describe both your system prompt (what instruction you gave the model) and any structural
     choices (e.g., how you formatted the context, whether you filtered low-relevance chunks).
     Do not just say "I told it to use the documents" — show the actual instruction or explain
     the mechanism. -->

**System prompt grounding instruction:**
In my system prompt I tell the model to use only the information in the retrieved chunks and not to bring in any outside knowledge or guesses. The actual instruction says: "Use only the information in the provided context. Do not use outside knowledge, guesses, or general background knowledge," and to reply with "I don't have enough information on that." only when the chunks don't cover the question. A few other choices back this up: I send the model only the top 5 retrieved chunks as its "documents," I run it at a low temperature (0.1) so it doesn't get creative, and if nothing is retrieved the code returns the fallback line without even calling the model. I tested this with an off-topic question ("What is the capital of France?") and it correctly said it didn't have enough information instead of answering from memory.

**How source attribution is surfaced in the response:**
The sources are added by my code, not by the model. After the answer is generated, the app looks at the source name saved with each retrieved chunk, removes duplicates, and shows them in a separate "Sources" box in the Gradio app. Because the sources come from the chunks that were actually retrieved instead of from the model's own text, the model can't make up a source — the answer and the sources always come from the same set of documents.

---

## Evaluation Report

<!-- Run your 5 test questions from planning.md through your system and record the results.
     Be honest — a partially accurate or inaccurate result that you explain well is more
     valuable than a suspiciously perfect result. -->

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | What are the best study groups for Computer Science students at University of Minnesota?|The Computer Science Crew and other student organizations |The Computer Science Crew. | relevant | accurate|
| 2 |Which clubs at University of St. Thomas supports Computer Science students? |The Computer Science Club, colorStack |ColorStack at University of St. Thomas, Computer Science Club. | relevant|accurate |
| 3 | What resources are available for Computer Science students at Texas A&M University?| Course descriptions, study groups, and academic support centers | CSCE - Computer Sci & Engr.| off target | in accurate|
| 4 | Does the University of St. Thomas provide ways for students to connect through academic organizations? |Yes. Students can use TommieLink to find registered student organizations, including academic and professional groups related to their fields of study. |The University of St. Thomas provides ways for students to connect through various academic organizations, including: Academic Quiz Bowl Club, Accounting Club, American Society of Mechanical Engineers, Aquinas Scholars Honors Program, Noyce Teacher Education Scholars Program, Opus College of Business Undergraduate Program, Student Nursing Association, Students for Human Life, Supply Chain & Operations Management Club, Teachers Educating and Creating Hope, Tennis Bar Association. | partially relevant| partially accurate|
| 5 |Are there class specific study groups for Computer Science at University of Minnesota?  |Yes, there are several class-specific study groups available through the Computer Science Crew and other student organizations | I don't have enough information on that.| off target| accurate(I didn't provide enough information on that.) |

**Retrieval quality:** Relevant / Partially relevant / Off-target  
**Response accuracy:** Accurate / Partially accurate / Inaccurate

---

## Failure Case Analysis

<!-- Identify at least one question where retrieval or generation did not work as expected.
     Write a specific explanation of *why* it failed, tied to a part of the pipeline.

     "The answer was wrong" is not an explanation.

     "The relevant information was split across a chunk boundary, so retrieval returned
     only half the context — the model didn't have enough to answer correctly" is an explanation.

     "The embedding model treated the professor's nickname as out-of-vocabulary and returned
     results from an unrelated review" is an explanation. -->

**Question that failed:**
What resources are available for Computer Science students at Texas A&M University?
**What the system returned:**
CSCE - Computer Sci & Engr.
**Root cause (tied to a specific pipeline stage):**
Retrieval failed because the vector search returned chunks from unrelated Texas A&M course catalog entries (CSCE descriptions). This likely happened because the embedding model prioritized keyword similarity around “Computer Science” and “courses,” causing it to retrieve academic catalog content rather than student organizations or academic support centers
**What you would change to fix it:**
Add metadata filtering; When retrieving, restrict by source type.


---

## Spec Reflection

<!-- Reflect on how planning.md shaped your implementation.
     Answer both questions with at least 2–3 sentences each. -->

**One way the spec helped you during implementation:**
The planning.md file provided a clear structure for the entire RAG pipeline, especially the chunking strategy and retrieval settings. Defining the chunk size (300–500 tokens) and overlap (50 tokens) early helped guide how I implemented the chunk_text function and how I validated output during debugging. It also made it easier to evaluate whether the system was working correctly because I had predefined expectations for chunk quality and retrieval depth.
**One way your implementation diverged from the spec, and why:**
During implementation, I diverged from the original plan of using live web scraping for document ingestion and switched to using sources.txt files instead. This change was necessary because several sources (such as Reddit and university directory pages) were either blocked, dynamically rendered, or produced incomplete HTML content. Using local files made the pipeline more reliable, reproducible, and easier to debug, especially when validating chunk quality and retrieval behavior.

---

## AI Usage

<!-- Describe at least 2 specific instances where you used an AI tool during this project.
     For each: what did you give the AI as input, what did it produce, and what did you
     change, override, or direct differently?

     "I used Claude to help me code" is not sufficient.
     "I gave Claude my Chunking Strategy section from planning.md and asked it to implement
     chunk_text(). It returned a function using a fixed character split. I overrode the
     chunk size from 500 to 200 because my documents are short reviews, not long guides." -->

**Instance 1**

- *What I gave the AI:* My grounding requirement from planning.md (the system should only answer from the retrieved chunks and show its sources) and the Gradio interface skeleton, and I asked it to write the generation step and wire it to the UI.
- *What it produced:* A `rag_gradio_app.py` with a system prompt that only allows answers from the retrieved context, a Groq call to llama-3.3-70b-versatile, and a Gradio app that shows the answer and a separate list of sources.
- *What I changed or overrode:* The first version's grounding prompt was too strict — it refused questions it could actually answer, like "What are the best study groups for CS at UVM?", just because of the word "best." I had the prompt changed so it answers with whatever the context supports and only refuses when nothing relevant is found. I then checked that an off-topic question ("What is the capital of France?") still gets refused.

**Instance 2**

- *What I gave the AI:* My retrieval plan from planning.md (all-MiniLM-L6-v2, top 5 chunks, stored in ChromaDB) along with my existing ingestion and chunking code, and I asked it to build the embedding and storage step.
- *What it produced:* A `rag_embed_and_store.py` that reuses my chunking functions, embeds every chunk with all-MiniLM-L6-v2, and stores the chunks in a ChromaDB collection with their source names as metadata.
- *What I changed or overrode:* The first time I ran a query it crashed because the code asked ChromaDB to "include" the ids, which my version of ChromaDB doesn't allow in that list. I had that removed so queries work, and I made sure the collection name and metadata keys matched what the query app was looking for.
