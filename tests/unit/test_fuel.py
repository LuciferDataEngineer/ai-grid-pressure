from gridpressure.fuel import dispatch_class, fuel_chart, fuel_group


def test_battery_is_storage_before_it_can_look_renewable():
    assert fuel_group("Battery Storage", "Storage", "Grid") == "storage"
    assert fuel_chart("Battery Storage", "storage") == "Storage"


def test_known_fuels():
    assert fuel_group("Wind", "Renewable", "Onshore") == "renewable"
    assert fuel_chart("Wind", "renewable") == "Wind"
    assert fuel_group("Fossil", "Combustion", "Black Coal") == "fossil"
    assert fuel_chart("Fossil", "fossil", "Black Coal") == "Coal"
    assert fuel_chart("Fossil", "fossil", "Brown Coal") == "Brown coal"
    assert fuel_chart("Fossil", "fossil", "Natural Gas") == "Gas"
    assert fuel_chart("Fossil", "fossil", "Coal Seam Methane") == "Gas"
    assert fuel_chart("Fossil", "fossil", "Diesel") == "Other fossil"
    assert fuel_group("Hydro", "Renewable", "Run of River") == "renewable"
    assert fuel_chart("Hydro", "renewable") == "Hydro"


def test_blank_is_unclassified_not_a_guess():
    assert fuel_group("", "", "") == "unclassified"
    assert dispatch_class("Generating Unit") == "generating"
    assert dispatch_class("Load") == "load"
    assert dispatch_class("Bidirectional Unit") == "bidirectional"
