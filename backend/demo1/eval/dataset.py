"""
Ground truth Q&A pairs for ParaIQ RAG evaluation.
All questions are drawn from documents known to exist in the ChromaDB vector store.
Run seed_vector_store.py first if the store is empty.
"""

EVAL_DATASET = [
    {
        "question": "What was Alexander Vance charged with stealing and from whom?",
        "ground_truth": "Alexander Vance stole $750,000 from Citywide Venture Partners.",
    },
    {
        "question": "What court issued the indictment in the Southern District of New York case?",
        "ground_truth": "A grand jury in the Southern District of New York issued the indictment.",
    },
    {
        "question": "What was the outcome for the defendant convicted of wire fraud?",
        "ground_truth": "The defendant was convicted of wire fraud.",
    },
    {
        "question": "What did the court do with all charges in the dismissal case?",
        "ground_truth": "The court dismissed all charges with prejudice.",
    },
    {
        "question": "What was Maria Chen's lawsuit about?",
        "ground_truth": "The plaintiff Maria Chen filed a wrongful termination suit against her employer.",
    },
    {
        "question": "What law governs the agreement described in the contract documents?",
        "ground_truth": "The agreement is governed by the laws of the State of New York.",
    },
    {
        "question": "What did Meridian Capital Group get charged with in March 2024?",
        "ground_truth": "On March 15, 2024, Meridian Capital Group LLC was charged by regulators.",
    },
    {
        "question": "What sentence did Judge Rakoff give Franklin Estrada?",
        "ground_truth": "Judge Rakoff sentenced Franklin Estrada to 5 years for wire fraud.",
    },
    {
        "question": "What did Goldman Sachs do with its Microsoft price target?",
        "ground_truth": "Goldman Sachs raised its 12-month price target for Microsoft.",
    },
    {
        "question": "What revenue did Apple report in the quarterly earnings document?",
        "ground_truth": "Apple Inc. reported record quarterly revenue of $123.9 billion.",
    },
    {
        "question": "What did the Federal Reserve decide about interest rates?",
        "ground_truth": "The Federal Reserve held interest rates steady at 5.25%-5.50%.",
    },
    {
        "question": "What did the contractor fail to do at the construction site?",
        "ground_truth": "The contractor failed to complete the structural reinforcement work.",
    },
    {
        "question": "What type of document is marked as confidential attorney work product?",
        "ground_truth": "A forensic analysis document is marked as confidential attorney work product.",
    },
    {
        "question": "What did the parties file regarding the case schedule?",
        "ground_truth": "The parties filed a joint scheduling order.",
    },
    {
        "question": "What statute was cited in the Estrada wire fraud sentencing?",
        "ground_truth": "Judge Rakoff sentenced Estrada for wire fraud under 18 U.S.C.",
    },
]
