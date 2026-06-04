import os
import pytest
from gitagent_anatomy_visualizer import plot_anatomy

def test_plot_anatomy_generates_png():
    json_path = "shap_diagnostics/trade_anatomy_1360716987.json"
    expected_png = "shap_diagnostics/trade_anatomy_1360716987.png"

    # Remove output if it exists
    if os.path.exists(expected_png):
        os.remove(expected_png)

    assert os.path.exists(json_path), f"Test data {json_path} missing"

    # Run the function
    plot_anatomy(json_path)

    # Check if PNG was created
    assert os.path.exists(expected_png), "PNG file was not created"

    # Clean up
    if os.path.exists(expected_png):
        os.remove(expected_png)

def test_plot_anatomy_missing_file():
    # Should not raise exception
    plot_anatomy("non_existent_file.json")
