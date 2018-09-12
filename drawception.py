# -*- coding: utf-8 -*-
import json
import os
import re
import requests
import zipfile
from bs4 import BeautifulSoup
from threading import Thread


### Função que realiza o empacotamento das arquivos
def make_zip(folder):
    folder = os.path.basename(folder)
    drawception_zip = zipfile.ZipFile('drawception.zip', 'w', compression=zipfile.ZIP_DEFLATED)

    for foldername, subfolders, files in os.walk(folder):
        for file in files:
            print('compacting {}'.format(os.path.join(foldername, file)))
            drawception_zip.write(os.path.join(foldername, file))
    drawception_zip.close()


### Função que realiza o escape de carcteres especiais, recebe a string e retorna o valor livre de carcteres especiais
def clean(string):
    regex_special_char = re.compile(r'''(\?|\.|\||!|á|é|í|ó|ú|ç|ã|\\|/|\(|\)|{|}|\[|]|\+|-|@|\#|\$|%|&|\*|;|:|°|,|
    º|"|\'|´|'|\^|~|\s+|)''', re.IGNORECASE|re.DOTALL|re.VERBOSE)

    new_string = regex_special_char.sub('', string)
    return new_string


### Função que realiza o download das imagens
def download_image(image_name, image_url):

    ### Tenta criar um arquivo da imagem, caso ocorra algum erro, passa para a pŕoxima etapa.
    try:
        with open(image_name, 'wb') as png:

            image_download = requests.get(image_url)
            image_download.raise_for_status()

            for chunk in image_download.iter_content(100000):
                png.write(chunk)

    except Exception as error:
        print(error)


### Função que realiza o parsing e coleta de dados
def scrapy(player):

    ### Preparação da lista que armazenará os dados que serão passados para o JSON do usuário
    images_list = []

    ### Cria uma pasta para cada usuário, caso não exista
    ### O nome do usuário é passado para o filtro de caracters especiais
    player_dir = os.path.join(dir_name, clean(str(player.text)).replace(' ', '_'))
    os.makedirs(player_dir, exist_ok=True)

    ### Itera sobre as duas primeiras páginas de desenhos do usuário, totalizando assim 36 desenhos, caso existam
    for page in range(1, 3):

        ### Acessa a página de desenhos do usuário, caso ocorra algum erro, passa para a pŕoxima etapa.
        try:
            profile = requests.get(base_url + player.get('href') + 'drawings/{}/'.format(page))
            profile.raise_for_status()

            ### Realiza o parsing da página do usuário, caso ocorra algum erro, passa para a pŕoxima etapa.
            try:
                soup = BeautifulSoup(profile.text, 'html.parser')

                ### Pega a lista de imagens
                images = soup.select('.thumbpanel-container a')

                ### Percorre por todas as imagens
                for image in images:

                    ### Pega a url do jogo a qual a imagem pertence
                    game_url = base_url + image.get('href')

                    ### Coleta a url da imagem e passa para a função que realiza o download
                    ### O nome da imagem é passado para o filtro de caracteres especiais
                    for i in image.select('img'):
                        image_name = os.path.join(player_dir, '{}.png'.format(clean(str(i.get('alt'))).replace(' ', '_')))
                        image_url = i.get('src')
                        print('downloading {}'.format(image_name))

                        ### Função que realiza o download da imagem
                        download_image(image_name, image_url)

                        print('finishing {}'.format(image_name))

                    ### Captura as informações do jogo onde a imagem foi criada, caso ocorra algum erro,
                    ### passa para a pŕoxima etapa.
                    try:
                        game_info = requests.get(game_url)
                        game_info.raise_for_status()

                        soup = BeautifulSoup(game_info.text, 'html.parser')
                        name = [str(text.text).replace('\n', '').strip() for text in soup.select('.text-center h1')][0]
                        properties = [text.text for text in soup.select('.text-center small span')]

                        views = properties[0]
                        favorites = properties[2]
                        duration = properties[4]

                    ### Em caso de erro, atribui valores vazios para serem passados ao JSON
                    except Exception as error:
                        print(error)
                        views = ''
                        favorites = ''
                        duration = ''
                        name = ''
                        image_name = ''

                    ### Independente do resultado, gera os resultados que serão passados para a criação do JSON do
                    ### usuário.
                    finally:
                        images_list.append({'image': image_name,
                                            'game': {'views': views,
                                                     'favorites': favorites,
                                                     'duration': duration,
                                                     'url': game_url,
                                                     'name': name}})

            except Exception as error:
                print(error)
        except Exception as error:
            print(error)

    ### Após a finalização da coleta de dados e imagens do usuário, seu JSON é gerado
    player_json = json.dumps({'player': player.text,
                              'images': images_list})

    ### Armazena o JSON com as informações do usuário em seu diretório, junto com seus desenhos.
    with open(os.path.join(player_dir, '{}.json'.format(str(player.text).replace(' ', '_'))), 'w') as j:
        j.write(player_json)


if __name__ == '__main__':

    ### Acessa a url com o ranking, se ocorrer algum erro o programa finaliza imediatamente.
    base_url = 'https://drawception.com'
    try:
        leaderboard = requests.get(base_url + '/leaderboard/')
        leaderboard.raise_for_status()
    except Exception as error:
        print(error)
        exit(1)

    ### Cria um diretório para guardar as imagens caso não exista:
    dir_name = 'images'
    os.makedirs(dir_name, exist_ok=True)

    ### Realiza o parsing da página
    soup = BeautifulSoup(leaderboard.text, 'html.parser')

    ### Coleta todos os elementos rankeados da página.
    leaderboard_home = soup.select('.col-md-6 .table.table-striped.table-hover a')

    ### Separa apenas os players independente do ranking que eles estejam e os armazena em uma lista
    players = []
    for elemnet in leaderboard_home:
        if str(elemnet.get('href')).startswith('/player/'):
            players.append(elemnet)

    ### Prepara uma lista e um contador para trabalhar com Threads na coleta dos dados
    threads_list = []
    threads = 0

    ### Captura os 50 primeiros "Most Followed all time" (Top players nao existe)
    for player in players[10:]:

        ### Inicia a coleta dos dados através iniciando uma thread por usuário a ser coletado.
        ### O número de threads permitido será 2x a quantidade de núcleos da cpu
        ### Ao atingir o número limite, o programa para de criar novas threads e aguarda a finalização das vigentes
        ### Para evitar sobrecarga no sistema e no site.
        thread = Thread(target=scrapy, args=(player,))
        threads_list.append(thread)
        thread.start()
        threads += 1
        if threads == os.cpu_count() * 2:
            for thread in threads_list:
                thread.join()
            threads_list = []
            threads = 0

    ### Aguarda a finalização das últimas threads
    for thread in threads_list:
        thread.join()

    ### Compacta todos os arquivos coletados
    make_zip('images')
