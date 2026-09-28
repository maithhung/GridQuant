from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest

from gridquant.collectors.energy_charts import fetch_price_response


def test_fetch_preserves_bytes_and_uses_timeout() -> None:
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b'{"original": true}\n'

    with patch(
        "gridquant.collectors.energy_charts.urlopen", return_value=response
    ) as request:
        result = fetch_price_response("2023-02-15", "2023-02-16")

    assert result == b'{"original": true}\n'
    request.assert_called_once()
    assert request.call_args.kwargs == {"timeout": 30}
    url = urlsplit(request.call_args.args[0])
    assert url.scheme == "https"
    assert url.netloc == "api.energy-charts.info"
    assert url.path == "/v2/price"
    assert parse_qs(url.query) == {
        "bzn": ["DE-LU"],
        "start": ["2023-02-15"],
        "end": ["2023-02-16"],
    }
    response.__exit__.assert_called_once()


def test_fetch_propagates_timeout_without_retrying() -> None:
    with (
        patch(
            "gridquant.collectors.energy_charts.urlopen", side_effect=TimeoutError
        ) as request,
        pytest.raises(TimeoutError),
    ):
        fetch_price_response("2023-02-15", "2023-02-15")

    request.assert_called_once()
