"""Tests for app.py"""



class TestCreateApp:
    def test_app_created(self, flask_app):
        assert flask_app is not None

    def test_blueprints_registered(self, flask_app):
        bp_names = [bp.name for bp in flask_app.iter_blueprints()]
        assert "github_bp" in bp_names
        assert "taiga_bp" in bp_names
        assert "excel_bp" in bp_names

    def test_github_webhook_route_exists(self, flask_app):
        rules = [rule.rule for rule in flask_app.url_map.iter_rules()]
        assert "/webhook/github" in rules

    def test_taiga_webhook_route_exists(self, flask_app):
        rules = [rule.rule for rule in flask_app.url_map.iter_rules()]
        assert "/webhook/taiga" in rules

    def test_excel_webhook_route_exists(self, flask_app):
        rules = [rule.rule for rule in flask_app.url_map.iter_rules()]
        assert "/webhook/excel" in rules

    def test_testing_config(self, flask_app):
        assert flask_app.config["TESTING"] is True
