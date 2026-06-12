import asyncio
from unittest.mock import MagicMock, patch
import pytest
import sniffio

class MockAsyncHttpxClientWrapper:
    def __init__(self, *args, **kwargs):
        pass
    def __del__(self):
        pass
    async def aclose(self):
        pass
    @property
    def is_closed(self):
        return False

def test_neuter_async_httpx_del_logic():
    from agent.auxiliary_client import neuter_async_httpx_del

    # Mock the SDK class
    with patch("openai._base_client.AsyncHttpxClientWrapper", MockAsyncHttpxClientWrapper):
        # Reset patch flag if it exists from other tests
        if hasattr(MockAsyncHttpxClientWrapper, "_hermes_patched"):
            del MockAsyncHttpxClientWrapper._hermes_patched

        neuter_async_httpx_del()

        # Test 1: Capture loop in __init__
        loop1 = asyncio.new_event_loop()
        try:
            with patch("asyncio.get_running_loop", return_value=loop1):
                client = MockAsyncHttpxClientWrapper()
                assert client._hermes_creation_loop is loop1
        finally:
            loop1.close()

        # Test 2: __del__ schedules cleanup on SAME loop
        loop2 = asyncio.new_event_loop()
        try:
            client = MockAsyncHttpxClientWrapper()
            client._hermes_creation_loop = loop2
            client.aclose = MagicMock()

            with patch("asyncio.get_running_loop", return_value=loop2), \
                 patch("sniffio.current_async_library", return_value="asyncio"):
                # We need to mock loop2.create_task because we're calling __del__ manually
                loop2.create_task = MagicMock()

                MockAsyncHttpxClientWrapper.__del__(client)

                loop2.create_task.assert_called_once()
        finally:
            loop2.close()

        # Test 3: __del__ skips cleanup on DIFFERENT loop
        loop3a = asyncio.new_event_loop()
        loop3b = asyncio.new_event_loop()
        try:
            client = MockAsyncHttpxClientWrapper()
            client._hermes_creation_loop = loop3a

            with patch("asyncio.get_running_loop", return_value=loop3b), \
                 patch("sniffio.current_async_library", return_value="asyncio"):
                loop3b.create_task = MagicMock()

                MockAsyncHttpxClientWrapper.__del__(client)

                loop3b.create_task.assert_not_called()
        finally:
            loop3a.close()
            loop3b.close()

        # Test 4: __del__ skips cleanup on NON-asyncio runtime
        loop4 = asyncio.new_event_loop()
        try:
            client = MockAsyncHttpxClientWrapper()
            client._hermes_creation_loop = loop4

            with patch("asyncio.get_running_loop", return_value=loop4), \
                 patch("sniffio.current_async_library", return_value="trio"):
                loop4.create_task = MagicMock()

                MockAsyncHttpxClientWrapper.__del__(client)

                loop4.create_task.assert_not_called()
        finally:
            loop4.close()

        # Test 5: __del__ skips cleanup when NO async library found
        loop5 = asyncio.new_event_loop()
        try:
            client = MockAsyncHttpxClientWrapper()
            client._hermes_creation_loop = loop5

            with patch("sniffio.current_async_library", side_effect=sniffio.AsyncLibraryNotFoundError):
                loop5.create_task = MagicMock()
                MockAsyncHttpxClientWrapper.__del__(client)
                loop5.create_task.assert_not_called()
        finally:
            loop5.close()
