from swane.config.config_enums import RegistrationEngine


class TestRegistrationEngineEnum:
    def test_members_exist(self):
        assert {m.name for m in RegistrationEngine} == {"FSL", "SYNTH", "ANTS"}

    def test_values_are_human_labels(self):
        # values are user-facing strings, not the bare member names
        assert all(isinstance(m.value, str) and m.value for m in RegistrationEngine)
