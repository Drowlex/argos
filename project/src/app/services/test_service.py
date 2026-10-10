class TestService(object):
    _instance = None

    def __new__(cls):
        """
        ? Patrón Singleton
        """
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    """docstring for TestService."""
    def __init__(self):
        super(TestService, self).__init__()

    def suma(self, a, b) -> int:
        return a+b


test_service = TestService()