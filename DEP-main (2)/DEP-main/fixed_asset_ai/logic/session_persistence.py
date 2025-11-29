"""
Session State Persistence for Fixed Asset AI

Allows saving and restoring session state to/from files,
so users don't lose work on page refresh.
"""

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import pandas as pd


SESSION_DIR = Path("sessions")
SESSION_DIR.mkdir(exist_ok=True)


def save_session(
    session_state: Dict[str, Any],
    session_id: str = None,
    session_dir: str = "sessions"
) -> str:
    """
    Save current session state to a file.

    Args:
        session_state: Streamlit session_state dict
        session_id: Optional ID (auto-generated if not provided)
        session_dir: Directory to save sessions

    Returns:
        Session ID that can be used to restore
    """
    Path(session_dir).mkdir(exist_ok=True)

    if not session_id:
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Extract serializable data from session state
    save_data = {
        "session_id": session_id,
        "saved_at": datetime.now().isoformat(),
        "tax_year": session_state.get("tax_year"),
        "strategy": session_state.get("strategy"),
        "taxable_income": session_state.get("taxable_income"),
        "de_minimis_limit": session_state.get("de_minimis_limit"),
        "use_acq_if_missing": session_state.get("use_acq_if_missing"),
        "audit_info": session_state.get("audit_info"),
        "critical_issue_count": session_state.get("critical_issue_count", 0),
    }

    # Save DataFrames separately as pickle
    dataframes = {}
    for key in ["classified_df", "fa_preview", "df_raw"]:
        if key in session_state and session_state[key] is not None:
            df = session_state[key]
            if isinstance(df, pd.DataFrame):
                dataframes[key] = df

    # Save metadata as JSON
    metadata_path = Path(session_dir) / f"{session_id}_meta.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=2, default=str)

    # Save DataFrames as pickle
    if dataframes:
        pickle_path = Path(session_dir) / f"{session_id}_data.pkl"
        with open(pickle_path, "wb") as f:
            pickle.dump(dataframes, f)

    return session_id


def load_session(
    session_id: str,
    session_dir: str = "sessions"
) -> Optional[Dict[str, Any]]:
    """
    Load session state from a file.

    Args:
        session_id: Session ID to load
        session_dir: Directory where sessions are saved

    Returns:
        Dictionary of session data, or None if not found
    """
    metadata_path = Path(session_dir) / f"{session_id}_meta.json"
    pickle_path = Path(session_dir) / f"{session_id}_data.pkl"

    if not metadata_path.exists():
        return None

    # Load metadata
    with open(metadata_path, "r", encoding="utf-8") as f:
        session_data = json.load(f)

    # Load DataFrames if they exist
    if pickle_path.exists():
        with open(pickle_path, "rb") as f:
            dataframes = pickle.load(f)
        session_data.update(dataframes)

    return session_data


def list_sessions(session_dir: str = "sessions") -> list:
    """
    List all available saved sessions.

    Args:
        session_dir: Directory where sessions are saved

    Returns:
        List of session metadata dictionaries
    """
    Path(session_dir).mkdir(exist_ok=True)
    sessions = []

    for meta_file in Path(session_dir).glob("*_meta.json"):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            sessions.append(meta)
        except Exception:
            continue

    # Sort by saved_at descending (newest first)
    sessions.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return sessions


def delete_session(session_id: str, session_dir: str = "sessions") -> bool:
    """
    Delete a saved session.

    Args:
        session_id: Session ID to delete
        session_dir: Directory where sessions are saved

    Returns:
        True if deleted, False if not found
    """
    metadata_path = Path(session_dir) / f"{session_id}_meta.json"
    pickle_path = Path(session_dir) / f"{session_id}_data.pkl"

    deleted = False
    if metadata_path.exists():
        metadata_path.unlink()
        deleted = True
    if pickle_path.exists():
        pickle_path.unlink()
        deleted = True

    return deleted


def auto_save_session(session_state: Dict[str, Any]) -> None:
    """
    Auto-save session with a standard auto-save ID.
    Overwrites previous auto-save.

    Args:
        session_state: Streamlit session_state dict
    """
    save_session(session_state, session_id="autosave")


def load_autosave() -> Optional[Dict[str, Any]]:
    """
    Load the auto-saved session if it exists.

    Returns:
        Session data or None
    """
    return load_session("autosave")


def has_autosave() -> bool:
    """
    Check if an auto-save exists.

    Returns:
        True if auto-save exists
    """
    return (Path("sessions") / "autosave_meta.json").exists()
