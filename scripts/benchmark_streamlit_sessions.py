"""Bounded anonymous Streamlit protocol load check, not an HTTP-shell benchmark.

No credentials, widget writes, database changes, or refresh actions are sent.
Script completion is measured; browser painting/network on a phone is not.
"""
import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from urllib.parse import urlparse
from websockets.asyncio.client import connect
from streamlit.proto.BackMsg_pb2 import BackMsg
from streamlit.proto.ForwardMsg_pb2 import ForwardMsg


async def session(base, query):
    start = perf_counter()
    socket = None
    messages = 0
    kinds = {}
    try:
        parsed = urlparse(base)
        ws_url = base.rstrip('/').replace('https://', 'wss://').replace('http://', 'ws://') + '/_stcore/stream'
        socket = await connect(ws_url, origin=f'{parsed.scheme}://{parsed.netloc}', subprotocols=['streamlit'], open_timeout=10)
        message = BackMsg()
        message.rerun_script.query_string = query
        await socket.send(message.SerializeToString())
        errors = []
        while True:
            raw = await asyncio.wait_for(socket.recv(), timeout=60)
            if raw is None:
                raise RuntimeError('socket_closed_before_completion')
            forward = ForwardMsg()
            forward.ParseFromString(raw)
            messages += 1
            kind = forward.WhichOneof('type')
            kinds[kind] = kinds.get(kind, 0) + 1
            if forward.HasField('delta') and forward.delta.HasField('new_element'):
                element = forward.delta.new_element
                if element.HasField('exception'):
                    errors.append(element.exception.type)
            if forward.HasField('script_finished'):
                return {'seconds': round(perf_counter()-start, 3), 'messages': messages,
                        'exception_types': errors, 'completion_code': forward.script_finished}
    except Exception as exc:
        return {'seconds': round(perf_counter()-start, 3), 'error_type': type(exc).__name__, 'messages': messages, 'message_types': kinds}
    finally:
        if socket:
            await socket.close()


async def main(args):
    result = {'base_url': args.url, 'scope': 'Anonymous server-script completion, not usable browser paint or authenticated roster concurrency',
              'single': await session(args.url, args.query)}
    result['concurrent'] = (await asyncio.gather(*(session(args.url, args.query) for _ in range(args.users)))) if not result['single'].get('error_type') else []
    result['concurrency_skipped'] = bool(result['single'].get('error_type'))
    result['users'] = args.users
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--query', default='view=decision-room&position=WR&players=Puka%20Nacua%7CJaxon%20Smith-Njigba&qb=4')
    parser.add_argument('--users', type=int, choices=range(1,11), default=10)
    parser.add_argument('--output', required=True)
    asyncio.run(main(parser.parse_args()))
