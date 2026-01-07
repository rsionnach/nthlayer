"""Tests for dashboards/models.py.

Tests for Grafana dashboard data models.
"""

from nthlayer.dashboards.models import (
    Dashboard,
    Panel,
    Row,
    Target,
    TemplateVariable,
)


class TestTarget:
    """Tests for Target dataclass."""

    def test_create_basic_target(self):
        """Test creating basic target with required fields."""
        target = Target(expr="up{job='test'}")

        assert target.expr == "up{job='test'}"
        assert target.legend_format == "{{label}}"
        assert target.ref_id == "A"
        assert target.interval is None
        assert target.instant is False

    def test_create_target_with_all_fields(self):
        """Test creating target with all fields."""
        target = Target(
            expr="rate(http_requests_total[5m])",
            legend_format="{{method}} {{status}}",
            ref_id="B",
            interval="1m",
            instant=True,
        )

        assert target.expr == "rate(http_requests_total[5m])"
        assert target.legend_format == "{{method}} {{status}}"
        assert target.ref_id == "B"
        assert target.interval == "1m"
        assert target.instant is True

    def test_to_dict_basic(self):
        """Test to_dict with basic target."""
        target = Target(expr="up")

        result = target.to_dict()

        assert result["expr"] == "up"
        assert result["legendFormat"] == "{{label}}"
        assert result["refId"] == "A"
        assert "interval" not in result
        assert "instant" not in result

    def test_to_dict_with_interval(self):
        """Test to_dict includes interval when set."""
        target = Target(expr="up", interval="30s")

        result = target.to_dict()

        assert result["interval"] == "30s"

    def test_to_dict_with_instant(self):
        """Test to_dict includes instant when True."""
        target = Target(expr="up", instant=True)

        result = target.to_dict()

        assert result["instant"] is True

    def test_to_dict_instant_false_not_included(self):
        """Test to_dict does not include instant when False."""
        target = Target(expr="up", instant=False)

        result = target.to_dict()

        assert "instant" not in result


class TestPanel:
    """Tests for Panel dataclass."""

    def test_create_basic_panel(self):
        """Test creating basic panel."""
        panel = Panel(
            title="Test Panel",
            targets=[Target(expr="up")],
        )

        assert panel.title == "Test Panel"
        assert len(panel.targets) == 1
        assert panel.panel_type == "timeseries"
        assert panel.id == 0

    def test_create_panel_with_all_fields(self):
        """Test creating panel with all fields."""
        panel = Panel(
            title="Complex Panel",
            targets=[Target(expr="up")],
            panel_type="gauge",
            description="A gauge panel",
            unit="percent",
            decimals=2,
            min=0,
            max=100,
            thresholds=[
                {"color": "green", "value": None},
                {"color": "yellow", "value": 70},
                {"color": "red", "value": 90},
            ],
            grid_pos={"h": 6, "w": 8, "x": 0, "y": 0},
        )

        assert panel.title == "Complex Panel"
        assert panel.panel_type == "gauge"
        assert panel.description == "A gauge panel"
        assert panel.unit == "percent"
        assert panel.decimals == 2
        assert panel.min == 0
        assert panel.max == 100
        assert len(panel.thresholds) == 3
        assert panel.grid_pos["w"] == 8

    def test_to_dict_basic_timeseries(self):
        """Test to_dict for basic timeseries panel."""
        panel = Panel(
            title="Requests",
            targets=[Target(expr="rate(http_requests_total[5m])")],
        )

        result = panel.to_dict()

        assert result["title"] == "Requests"
        assert result["type"] == "timeseries"
        assert len(result["targets"]) == 1
        assert result["gridPos"] == {"h": 8, "w": 12, "x": 0, "y": 0}
        assert result["options"]["tooltip"]["mode"] == "multi"
        assert result["options"]["legend"]["displayMode"] == "list"

    def test_to_dict_gauge_panel(self):
        """Test to_dict for gauge panel."""
        panel = Panel(
            title="CPU Usage",
            targets=[Target(expr="cpu_usage")],
            panel_type="gauge",
        )

        result = panel.to_dict()

        assert result["type"] == "gauge"
        assert result["options"]["showThresholdLabels"] is False
        assert result["options"]["showThresholdMarkers"] is True

    def test_to_dict_stat_panel(self):
        """Test to_dict for stat panel."""
        panel = Panel(
            title="Total Requests",
            targets=[Target(expr="http_requests_total")],
            panel_type="stat",
        )

        result = panel.to_dict()

        assert result["type"] == "stat"
        assert result["options"]["graphMode"] == "area"
        assert result["options"]["colorMode"] == "value"
        assert result["options"]["orientation"] == "auto"

    def test_to_dict_table_panel(self):
        """Test to_dict for table panel (no special options)."""
        panel = Panel(
            title="Data Table",
            targets=[Target(expr="up")],
            panel_type="table",
        )

        result = panel.to_dict()

        assert result["type"] == "table"
        assert "options" not in result

    def test_to_dict_with_description(self):
        """Test to_dict includes description."""
        panel = Panel(
            title="Test",
            targets=[Target(expr="up")],
            description="This is a test panel",
        )

        result = panel.to_dict()

        assert result["description"] == "This is a test panel"

    def test_to_dict_with_unit(self):
        """Test to_dict includes unit in fieldConfig."""
        panel = Panel(
            title="Memory",
            targets=[Target(expr="memory_bytes")],
            unit="bytes",
        )

        result = panel.to_dict()

        assert result["fieldConfig"]["defaults"]["unit"] == "bytes"

    def test_to_dict_with_decimals(self):
        """Test to_dict includes decimals in fieldConfig."""
        panel = Panel(
            title="Percentage",
            targets=[Target(expr="percent")],
            decimals=2,
        )

        result = panel.to_dict()

        assert result["fieldConfig"]["defaults"]["decimals"] == 2

    def test_to_dict_with_min_max(self):
        """Test to_dict includes min/max in fieldConfig."""
        panel = Panel(
            title="Bounded",
            targets=[Target(expr="value")],
            min=0,
            max=100,
        )

        result = panel.to_dict()

        assert result["fieldConfig"]["defaults"]["min"] == 0
        assert result["fieldConfig"]["defaults"]["max"] == 100

    def test_to_dict_with_thresholds(self):
        """Test to_dict includes thresholds in fieldConfig."""
        thresholds = [
            {"color": "green", "value": None},
            {"color": "red", "value": 80},
        ]
        panel = Panel(
            title="Thresholds",
            targets=[Target(expr="value")],
            thresholds=thresholds,
        )

        result = panel.to_dict()

        assert result["fieldConfig"]["defaults"]["thresholds"]["mode"] == "absolute"
        assert result["fieldConfig"]["defaults"]["thresholds"]["steps"] == thresholds

    def test_to_dict_custom_grid_pos(self):
        """Test to_dict uses custom gridPos."""
        panel = Panel(
            title="Test",
            targets=[Target(expr="up")],
            grid_pos={"h": 10, "w": 24, "x": 0, "y": 5},
        )

        result = panel.to_dict()

        assert result["gridPos"]["h"] == 10
        assert result["gridPos"]["w"] == 24

    def test_to_dict_multiple_targets(self):
        """Test to_dict with multiple targets."""
        panel = Panel(
            title="Multi-query",
            targets=[
                Target(expr="metric_a", ref_id="A"),
                Target(expr="metric_b", ref_id="B"),
                Target(expr="metric_c", ref_id="C"),
            ],
        )

        result = panel.to_dict()

        assert len(result["targets"]) == 3
        assert result["targets"][0]["refId"] == "A"
        assert result["targets"][1]["refId"] == "B"
        assert result["targets"][2]["refId"] == "C"

    def test_to_dict_no_field_config_when_empty(self):
        """Test to_dict does not include fieldConfig when no defaults set."""
        panel = Panel(
            title="Basic",
            targets=[Target(expr="up")],
        )

        result = panel.to_dict()

        assert "fieldConfig" not in result


class TestRow:
    """Tests for Row dataclass."""

    def test_create_basic_row(self):
        """Test creating basic row."""
        row = Row(title="Overview")

        assert row.title == "Overview"
        assert row.collapsed is False
        assert row.panels == []
        assert row.id == 0

    def test_create_row_with_panels(self):
        """Test creating row with panels."""
        panels = [
            Panel(title="Panel 1", targets=[Target(expr="up")]),
            Panel(title="Panel 2", targets=[Target(expr="down")]),
        ]
        row = Row(title="Test Row", panels=panels)

        assert len(row.panels) == 2

    def test_create_collapsed_row(self):
        """Test creating collapsed row."""
        row = Row(title="Collapsed", collapsed=True)

        assert row.collapsed is True

    def test_to_dict(self):
        """Test to_dict for row."""
        row = Row(title="Test Row", collapsed=True)
        row.id = 5

        result = row.to_dict()

        assert result["id"] == 5
        assert result["type"] == "row"
        assert result["title"] == "Test Row"
        assert result["collapsed"] is True
        assert result["gridPos"] == {"h": 1, "w": 24, "x": 0, "y": 0}
        # Panels are siblings, not children in JSON
        assert result["panels"] == []


class TestTemplateVariable:
    """Tests for TemplateVariable dataclass."""

    def test_create_basic_variable(self):
        """Test creating basic template variable."""
        var = TemplateVariable(
            name="service",
            label="Service",
            query="label_values(up, service)",
        )

        assert var.name == "service"
        assert var.label == "Service"
        assert var.query == "label_values(up, service)"
        assert var.var_type == "query"
        assert var.datasource is None
        assert var.multi is False
        assert var.include_all is False

    def test_create_variable_with_all_fields(self):
        """Test creating variable with all fields."""
        var = TemplateVariable(
            name="env",
            label="Environment",
            query="label_values(env)",
            var_type="custom",
            datasource="prometheus",
            multi=True,
            include_all=True,
            current={"text": "prod", "value": "prod"},
        )

        assert var.var_type == "custom"
        assert var.datasource == "prometheus"
        assert var.multi is True
        assert var.include_all is True
        assert var.current["text"] == "prod"

    def test_to_dict_basic(self):
        """Test to_dict for basic variable."""
        var = TemplateVariable(
            name="job",
            label="Job",
            query="label_values(job)",
        )

        result = var.to_dict()

        assert result["name"] == "job"
        assert result["label"] == "Job"
        assert result["type"] == "query"
        assert result["query"] == "label_values(job)"
        assert result["multi"] is False
        assert result["includeAll"] is False
        assert "datasource" not in result
        assert "current" not in result

    def test_to_dict_with_datasource(self):
        """Test to_dict includes datasource."""
        var = TemplateVariable(
            name="var",
            label="Var",
            query="query",
            datasource="prometheus-prod",
        )

        result = var.to_dict()

        assert result["datasource"] == "prometheus-prod"

    def test_to_dict_with_current(self):
        """Test to_dict includes current value."""
        var = TemplateVariable(
            name="var",
            label="Var",
            query="query",
            current={"text": "All", "value": "$__all"},
        )

        result = var.to_dict()

        assert result["current"]["text"] == "All"
        assert result["current"]["value"] == "$__all"

    def test_to_dict_multi_and_include_all(self):
        """Test to_dict with multi and includeAll."""
        var = TemplateVariable(
            name="service",
            label="Service",
            query="query",
            multi=True,
            include_all=True,
        )

        result = var.to_dict()

        assert result["multi"] is True
        assert result["includeAll"] is True


class TestDashboard:
    """Tests for Dashboard dataclass."""

    def test_create_basic_dashboard(self):
        """Test creating basic dashboard."""
        dashboard = Dashboard(title="My Dashboard")

        assert dashboard.title == "My Dashboard"
        assert dashboard.panels == []
        assert dashboard.rows == []
        assert dashboard.template_variables == []
        assert dashboard.uid is None
        assert dashboard.timezone == "browser"
        assert dashboard.editable is True
        assert dashboard.time_from == "now-6h"
        assert dashboard.time_to == "now"
        assert dashboard.refresh == "30s"

    def test_create_dashboard_with_all_metadata(self):
        """Test creating dashboard with all metadata."""
        dashboard = Dashboard(
            title="Full Dashboard",
            uid="my-uid-123",
            description="A comprehensive dashboard",
            tags=["production", "api"],
            timezone="utc",
            editable=False,
            time_from="now-24h",
            time_to="now",
            refresh="1m",
        )

        assert dashboard.uid == "my-uid-123"
        assert dashboard.description == "A comprehensive dashboard"
        assert dashboard.tags == ["production", "api"]
        assert dashboard.timezone == "utc"
        assert dashboard.editable is False
        assert dashboard.time_from == "now-24h"
        assert dashboard.refresh == "1m"

    def test_to_dict_basic(self):
        """Test to_dict for basic dashboard."""
        dashboard = Dashboard(title="Test Dashboard")

        result = dashboard.to_dict()

        assert result["title"] == "Test Dashboard"
        assert result["panels"] == []
        assert result["editable"] is True
        assert result["timezone"] == "browser"
        assert result["tags"] == []
        assert result["time"] == {"from": "now-6h", "to": "now"}
        assert result["refresh"] == "30s"
        assert result["schemaVersion"] == 38
        assert result["version"] == 0
        assert "uid" not in result
        assert "description" not in result

    def test_to_dict_with_uid(self):
        """Test to_dict includes uid."""
        dashboard = Dashboard(title="Test", uid="test-uid")

        result = dashboard.to_dict()

        assert result["uid"] == "test-uid"

    def test_to_dict_with_description(self):
        """Test to_dict includes description."""
        dashboard = Dashboard(title="Test", description="Test description")

        result = dashboard.to_dict()

        assert result["description"] == "Test description"

    def test_to_dict_with_standalone_panels(self):
        """Test to_dict with standalone panels."""
        dashboard = Dashboard(
            title="Test",
            panels=[
                Panel(title="Panel 1", targets=[Target(expr="up")]),
                Panel(title="Panel 2", targets=[Target(expr="down")]),
            ],
        )

        result = dashboard.to_dict()

        assert len(result["panels"]) == 2
        assert result["panels"][0]["title"] == "Panel 1"
        assert result["panels"][1]["title"] == "Panel 2"
        # Check IDs are assigned
        assert result["panels"][0]["id"] == 1
        assert result["panels"][1]["id"] == 2

    def test_to_dict_standalone_panels_grid_layout(self):
        """Test standalone panels are laid out horizontally."""
        dashboard = Dashboard(
            title="Test",
            panels=[
                Panel(title="Panel 1", targets=[Target(expr="up")]),
                Panel(title="Panel 2", targets=[Target(expr="down")]),
            ],
        )

        result = dashboard.to_dict()

        # First panel at x=0
        assert result["panels"][0]["gridPos"]["x"] == 0
        # Second panel at x=12 (default width)
        assert result["panels"][1]["gridPos"]["x"] == 12

    def test_to_dict_with_rows(self):
        """Test to_dict with rows containing panels."""
        row = Row(
            title="Overview",
            panels=[
                Panel(title="Panel A", targets=[Target(expr="a")]),
                Panel(title="Panel B", targets=[Target(expr="b")]),
            ],
        )
        dashboard = Dashboard(title="Test", rows=[row])

        result = dashboard.to_dict()

        # Row + 2 panels
        assert len(result["panels"]) == 3
        assert result["panels"][0]["type"] == "row"
        assert result["panels"][0]["title"] == "Overview"
        assert result["panels"][1]["title"] == "Panel A"
        assert result["panels"][2]["title"] == "Panel B"

    def test_to_dict_row_panel_ids(self):
        """Test row and panel IDs are assigned sequentially."""
        row = Row(
            title="Row",
            panels=[Panel(title="Panel", targets=[Target(expr="up")])],
        )
        dashboard = Dashboard(title="Test", rows=[row])

        result = dashboard.to_dict()

        assert result["panels"][0]["id"] == 1  # Row
        assert result["panels"][1]["id"] == 2  # Panel

    def test_to_dict_row_grid_positions(self):
        """Test row and panel grid positions."""
        row = Row(
            title="Row",
            panels=[
                Panel(title="P1", targets=[Target(expr="up")]),
                Panel(title="P2", targets=[Target(expr="up")]),
            ],
        )
        dashboard = Dashboard(title="Test", rows=[row])

        result = dashboard.to_dict()

        # Row at y=0
        assert result["panels"][0]["gridPos"]["y"] == 0
        # Panels at y=1 (after row)
        assert result["panels"][1]["gridPos"]["y"] == 1
        assert result["panels"][2]["gridPos"]["y"] == 1
        # Panel x positions
        assert result["panels"][1]["gridPos"]["x"] == 0
        assert result["panels"][2]["gridPos"]["x"] == 12  # After first 12-width panel

    def test_to_dict_panel_wraps_to_next_row(self):
        """Test panels wrap to next row when width exceeds 24."""
        dashboard = Dashboard(
            title="Test",
            panels=[
                Panel(
                    title="P1",
                    targets=[Target(expr="up")],
                    grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
                ),
                Panel(
                    title="P2",
                    targets=[Target(expr="up")],
                    grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
                ),
                Panel(
                    title="P3",
                    targets=[Target(expr="up")],
                    grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
                ),
            ],
        )

        result = dashboard.to_dict()

        # First two panels on first row
        assert result["panels"][0]["gridPos"]["x"] == 0
        assert result["panels"][1]["gridPos"]["x"] == 12
        # Third panel wraps to next row
        assert result["panels"][2]["gridPos"]["x"] == 0
        assert result["panels"][2]["gridPos"]["y"] == result["panels"][1]["gridPos"]["y"] + 8

    def test_to_dict_with_template_variables(self):
        """Test to_dict with template variables."""
        dashboard = Dashboard(
            title="Test",
            template_variables=[
                TemplateVariable(name="service", label="Service", query="query1"),
                TemplateVariable(name="env", label="Environment", query="query2"),
            ],
        )

        result = dashboard.to_dict()

        assert "templating" in result
        assert len(result["templating"]["list"]) == 2
        assert result["templating"]["list"][0]["name"] == "service"
        assert result["templating"]["list"][1]["name"] == "env"

    def test_to_dict_no_templating_when_empty(self):
        """Test to_dict does not include templating when no variables."""
        dashboard = Dashboard(title="Test")

        result = dashboard.to_dict()

        assert "templating" not in result

    def test_to_dict_multiple_rows(self):
        """Test to_dict with multiple rows."""
        dashboard = Dashboard(
            title="Test",
            rows=[
                Row(title="Row 1", panels=[Panel(title="P1", targets=[Target(expr="up")])]),
                Row(title="Row 2", panels=[Panel(title="P2", targets=[Target(expr="up")])]),
            ],
        )

        result = dashboard.to_dict()

        # Row1, Panel1, Row2, Panel2
        assert len(result["panels"]) == 4
        assert result["panels"][0]["title"] == "Row 1"
        assert result["panels"][1]["title"] == "P1"
        assert result["panels"][2]["title"] == "Row 2"
        assert result["panels"][3]["title"] == "P2"

    def test_to_grafana_payload(self):
        """Test to_grafana_payload creates API format."""
        dashboard = Dashboard(title="Test Dashboard")

        result = dashboard.to_grafana_payload()

        assert "dashboard" in result
        assert result["dashboard"]["title"] == "Test Dashboard"
        assert result["overwrite"] is True
        assert result["message"] == "Generated by NthLayer"

    def test_to_dict_row_with_many_panels_spans_rows(self):
        """Test row with many panels that span multiple rows."""
        panels = [
            Panel(
                title=f"P{i}",
                targets=[Target(expr="up")],
                grid_pos={"h": 8, "w": 12, "x": 0, "y": 0},
            )
            for i in range(5)
        ]
        row = Row(title="Many Panels", panels=panels)
        dashboard = Dashboard(title="Test", rows=[row])

        result = dashboard.to_dict()

        # Row + 5 panels
        assert len(result["panels"]) == 6
        # Panels wrap at width 24
        # P0: x=0, P1: x=12, P2: x=0 (next y), P3: x=12, P4: x=0 (next y)
        assert result["panels"][1]["gridPos"]["x"] == 0
        assert result["panels"][2]["gridPos"]["x"] == 12
        assert result["panels"][3]["gridPos"]["x"] == 0

    def test_to_dict_mixed_rows_and_panels(self):
        """Test dashboard with both rows and standalone panels."""
        dashboard = Dashboard(
            title="Test",
            rows=[Row(title="Row", panels=[Panel(title="Row Panel", targets=[Target(expr="up")])])],
            panels=[Panel(title="Standalone", targets=[Target(expr="down")])],
        )

        result = dashboard.to_dict()

        # Row, Row Panel, Standalone Panel
        assert len(result["panels"]) == 3
        assert result["panels"][0]["type"] == "row"
        assert result["panels"][1]["title"] == "Row Panel"
        assert result["panels"][2]["title"] == "Standalone"


class TestDashboardLayoutEdgeCases:
    """Tests for dashboard layout edge cases."""

    def test_empty_row(self):
        """Test dashboard with empty row."""
        dashboard = Dashboard(
            title="Test",
            rows=[Row(title="Empty Row")],
        )

        result = dashboard.to_dict()

        assert len(result["panels"]) == 1
        assert result["panels"][0]["type"] == "row"

    def test_multiple_empty_rows(self):
        """Test dashboard with multiple empty rows."""
        dashboard = Dashboard(
            title="Test",
            rows=[Row(title="Row 1"), Row(title="Row 2"), Row(title="Row 3")],
        )

        result = dashboard.to_dict()

        # Each empty row should increment y position by 1
        assert result["panels"][0]["gridPos"]["y"] == 0
        assert result["panels"][1]["gridPos"]["y"] == 1
        assert result["panels"][2]["gridPos"]["y"] == 2

    def test_full_width_panels(self):
        """Test panels with full width (24)."""
        dashboard = Dashboard(
            title="Test",
            panels=[
                Panel(
                    title="Full1",
                    targets=[Target(expr="up")],
                    grid_pos={"h": 4, "w": 24, "x": 0, "y": 0},
                ),
                Panel(
                    title="Full2",
                    targets=[Target(expr="up")],
                    grid_pos={"h": 4, "w": 24, "x": 0, "y": 0},
                ),
            ],
        )

        result = dashboard.to_dict()

        # Each full-width panel should be on its own row
        assert result["panels"][0]["gridPos"]["x"] == 0
        assert result["panels"][0]["gridPos"]["y"] == 0
        assert result["panels"][1]["gridPos"]["x"] == 0
        assert result["panels"][1]["gridPos"]["y"] == 4  # After first panel's height

    def test_varied_panel_heights(self):
        """Test panels with different heights."""
        dashboard = Dashboard(
            title="Test",
            panels=[
                Panel(
                    title="Tall",
                    targets=[Target(expr="up")],
                    grid_pos={"h": 16, "w": 12, "x": 0, "y": 0},
                ),
                Panel(
                    title="Short",
                    targets=[Target(expr="up")],
                    grid_pos={"h": 4, "w": 12, "x": 0, "y": 0},
                ),
            ],
        )

        result = dashboard.to_dict()

        # Both start at y=0 (horizontally laid out)
        assert result["panels"][0]["gridPos"]["y"] == 0
        assert result["panels"][0]["gridPos"]["x"] == 0
        assert result["panels"][1]["gridPos"]["y"] == 0
        assert result["panels"][1]["gridPos"]["x"] == 12

    def test_row_with_no_panels_followed_by_row_with_panels(self):
        """Test empty row followed by row with panels."""
        dashboard = Dashboard(
            title="Test",
            rows=[
                Row(title="Empty"),
                Row(title="With Panels", panels=[Panel(title="P", targets=[Target(expr="up")])]),
            ],
        )

        result = dashboard.to_dict()

        # Empty Row at y=0, Row with Panels at y=1, Panel at y=2
        assert result["panels"][0]["gridPos"]["y"] == 0
        assert result["panels"][1]["gridPos"]["y"] == 1
        assert result["panels"][2]["gridPos"]["y"] == 2
