import argparse #Модуль argparse позволяет легко писать удобные интерфейсы командной строки. Программа определяет, какие аргументы ей требуются, а argparse выяснит, как их разобрать из вывода функции sys.argv.
import asyncio
import signal
import logging

from concurrent.futures import CancelledError

from torrent import Torrent
from  clientTorrent import TorrentClient


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('torrent',
                        help='the .torrent to download')
  #позволяет запускать  команду вида python cli.py Random.torrent

    args = parser.parse_args()
# сразу устанавливаю высокий уровень логгирования
    logging.basicConfig(level=logging.INFO)

    loop = asyncio.get_event_loop() #создаем обработчик событий
    client = TorrentClient(Torrent(args.torrent))
    task = loop.create_task(client.start()) #запуск потока внутри обработчика

    def signal_handler(*_):
        logging.info('Exiting, please wait until everything is shutdown...')
        client.stop()
        task.cancel()

    signal.signal(signal.SIGINT, signal_handler)
#Функция signal.signal() позволяет определять пользовательские обработчики, которые будут выполнены, когда сигнал получен.
    try:
        loop.run_until_complete(task)
    except CancelledError:
        logging.warning('Event loop was canceled')

main()
