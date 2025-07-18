"""Topic selector module for problem generation."""

import json
import random
import logging
from pathlib import Path
from typing import List

def select_random_topics() -> str:
    """Select 1-2 random topics from the topics.json file.
    
    Returns:
        str: Comma-separated list of selected topics
    
    Example:
        >>> select_random_topics()
        'Dynamic Programming, Trees'
    """
    try:
        # Look for topics.json in pg_agent/data directory
        topics_path = Path(__file__).parent.parent / "data" / "topics.json"
        
        if not topics_path.exists():
            raise FileNotFoundError(f"topics.json not found at {topics_path}")
            
        all_topics = json.loads(topics_path.read_text(encoding="utf-8"))
        all_topic_choices = []
        
        def extract_topics(data):
            """Recursively extract topics from nested dictionary."""
            if isinstance(data, dict):
                for value in data.values():
                    extract_topics(value)
            elif isinstance(data, list):
                all_topic_choices.extend(data)
        
        # Extract all topics recursively
        extract_topics(all_topics)
        
        # Select 1-2 random topics
        selected_topics = random.sample(all_topic_choices, k=random.randint(1, 2))
        topics = ", ".join(selected_topics)
        logging.info(f"Selected topics: '{topics}'")
        return topics
        
    except Exception as e:
        logging.error(f"Error selecting random topics: {str(e)}")
        # Return some default topics as fallback
        return "Dynamic Programming, Data Structures"

def topic_selector_node(state):
    """LangGraph node: selects topics and adds them to the state."""
    topics = select_random_topics()
    return {"topics": topics}

# Example usage
if __name__ == "__main__":
    print("Selected topics:", select_random_topics()) 