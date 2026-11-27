import httpx
import pytest
from validate_dual_stream import download_public_object

@pytest.mark.asyncio
async def test_gcs_download_does_not_send_relay_authorization():
    seen=[]
    async def handler(request):
        seen.append(request)
        assert 'authorization' not in request.headers
        return httpx.Response(200,content=b'object bytes')
    assert await download_public_object('https://storage.googleapis.com/citra-ai-events/example',httpx.MockTransport(handler))==b'object bytes'
    assert len(seen)==1

@pytest.mark.asyncio
async def test_failed_gcs_download_is_not_counted_verified():
    async def handler(request):return httpx.Response(403)
    with pytest.raises(httpx.HTTPStatusError):
        await download_public_object('https://storage.googleapis.com/citra-ai-events/example',httpx.MockTransport(handler))
