import asyncio
import json
import logging
import os

from github import Github
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO_NAME = os.getenv("REPO_NAME")
CATALOG_FILE = "docs/catalog/catalog.json"

lock = asyncio.Lock()


async def get_catalog_data():
    """Gets and parses the catalog data from the local filesystem."""
    try:
        with open(CATALOG_FILE, "r", encoding="utf-8") as f:
            catalog_data = json.load(f)
        return catalog_data
    except FileNotFoundError:
        return {"items": []}
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding catalog.json: {e}")
        return None
    except Exception as e:
        logging.error(f"Error getting catalog locally: {e}")
        return None


async def update_catalog_data(new_data):
    """Updates the catalog data on the local filesystem and optionally on GitHub."""
    # 1. Update local catalog.json
    try:
        os.makedirs(os.path.dirname(CATALOG_FILE), exist_ok=True)
        with open(CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(new_data, f, indent=2, ensure_ascii=False)
        logging.info("Local catalog.json updated successfully.")
    except Exception as e:
        logging.error(f"Error updating local catalog.json: {e}")
        return False

    # 2. Optionally update catalog.json on GitHub
    if GITHUB_TOKEN and REPO_NAME:
        try:
            g = Github(GITHUB_TOKEN)
            # Assuming REPO_NAME is in format "owner/repo"
            repo = g.get_repo(REPO_NAME)

            contents = repo.get_contents(CATALOG_FILE)

            # Encode new_data to JSON string
            new_content_str = json.dumps(new_data, indent=2, ensure_ascii=False)

            repo.update_file(
                path=CATALOG_FILE,
                message="Update catalog.json via bot",
                content=new_content_str,
                sha=contents.sha,
            )
            logging.info(
                f"catalog.json updated successfully on GitHub in repository {REPO_NAME}."
            )
            return True
        except Exception as e:
            logging.error(f"Error updating catalog.json on GitHub: {e}")
            return False
    else:
        logging.info(
            "GitHub token or repository name not provided. Skipping GitHub update."
        )
        return True  # Local update was successful, so return True
