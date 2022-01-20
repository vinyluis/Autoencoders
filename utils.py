# FUNÇÕES DE APOIO PARA O AUTOENCODER

import os
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
from datetime import datetime
from datetime import timedelta

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Silencia o TF (https://stackoverflow.com/questions/35911252/disable-tensorflow-debugging-information)
import tensorflow as tf

from sklearn.metrics import accuracy_score as accuracy

#%% FUNÇÕES DE APOIO

def get_time_string(mode = "complete", days_offset = 0):
    # Prepara a string de data e hora conforme necessário

    #horário atual
    now = datetime.now()
    now = now + timedelta(days = days_offset) # adiciona um offset de x dias
    yr = str(now.year)
    mt = str(now.month)
    dy = str(now.day)
    
    if(len(mt)==1):
        mt = "0" + mt
    
    if(len(dy)==1):
        dy = "0" + dy
    
    m = str(now.minute)
    h = str(now.hour)
    s = str(now.second)
    
    if(len(m)==1):
        m = "0" + m
    if(len(h)==1):
        h = "0" + h
    if(len(s)==1):
        s = "0" + s
    
    if(mode == "complete"):
        st = dy + "-" + mt + "-" + yr + " " + h + ":" + m + ":" + s
        return st
    
    if(mode == "normal"):
        st = dy + "-" + mt + "-" + yr
        return st
    
    if(mode == "file"):
        st = yr+mt+dy
        return st
    
def generate_images(generator, img_input, save_destination = None, filename = None):
    img_predict = generator(img_input, training=True)
    f = plt.figure(figsize=(15,15))
    
    display_list = [img_input[0], img_predict[0]]
    title = ['Input Image', 'Predicted Image']
    
    for i in range(2):
        plt.subplot(1, 2, i+1)
        plt.title(title[i])
        # getting the pixel values between [0, 1] to plot it.
        plt.imshow(display_list[i] * 0.5 + 0.5)
        plt.axis('off')
    f.show()
    
    if save_destination != None and filename != None:
        f.savefig(save_destination + filename)

    return f

def plot_losses(loss_df, plot_ma = True, window = 100):
    
    # Plota o principal
    f = plt.figure()
    sns.lineplot(x = range(loss_df.shape[0]), y = loss_df["Loss G"])
    sns.lineplot(x = range(loss_df.shape[0]), y = loss_df["Loss D"])
    
    # Plota as médias móveis
    if plot_ma:
        
        lossG_ma = loss_df["Loss G"].rolling(window = window, min_periods = 1).mean()
        lossD_ma = loss_df["Loss D"].rolling(window = window, min_periods = 1).mean()
        sns.lineplot(x = range(loss_df.shape[0]), y = lossG_ma)
        sns.lineplot(x = range(loss_df.shape[0]), y = lossD_ma)
        plt.legend(["Loss G", "Loss D", "Loss G - MA", "Loss D - MA"])
    else:
        plt.legend(["Loss G", "Loss D"])
    
    f.show()
    
    return f

def evaluate_accuracy(generator, discriminator, test_ds, y_real, y_pred, window = 100):
    
    # Gera uma imagem-base
    for img_real in test_ds.take(1):
        target = img_real

        # A partir dela, gera uma imagem sintética
        img_fake = generator(img_real, training = True)

        # Avalia ambas
        disc_real = discriminator([img_real, target], training = True)
        disc_fake = discriminator([img_fake, target], training = True)

        # Para o caso de ser um discriminador PatchGAN, tira a média
        disc_real = np.mean(disc_real)
        disc_fake = np.mean(disc_fake)

        # Aplica o threshold
        disc_real = 1 if disc_real > 0.5 else 0
        disc_fake = 1 if disc_fake > 0.5 else 0

        # Acrescenta a observação real como y_real = 1
        y_real.append(1)
        y_pred.append(disc_real)

        # Acrescenta a observação fake como y_real = 0
        y_real.append(0)
        y_pred.append(disc_fake)
        
        # Calcula a acurácia pela janela
        if len(y_real) > window:
            acc = accuracy(y_real[-window:], y_pred[-window:])    
        else:
            acc = accuracy(y_real, y_pred)

        return y_real, y_pred, acc

#%% FUNÇÕES DO DATASET

def load(image_file):
    image = tf.io.read_file(image_file)
    image = tf.image.decode_jpeg(image)
    image = tf.cast(image, tf.float32)
    return image

def normalize(input_image):
    # normalizing the images to [-1, 1]
    input_image = (input_image / 127.5) - 1
    return input_image

def resize(input_image, height, width):
    input_image = tf.image.resize(input_image, [height, width], method=tf.image.ResizeMethod.NEAREST_NEIGHBOR)
    return input_image

def random_crop(input_image, img_size, num_channels):
    cropped_image = tf.image.random_crop(value = input_image, size = [img_size, img_size, num_channels])
    return cropped_image

def random_jitter(input_image, img_size, num_channels):
    # resizing to 286 x 286 x 3
    new_size = int(img_size * 1.117)
    input_image = resize(input_image, new_size, new_size)
    # randomly cropping to IMGSIZE x IMGSIZE x 3
    input_image = random_crop(input_image, img_size, num_channels)
    
    if tf.random.uniform(()) > 0.5:
        # random mirroring
        input_image = tf.image.flip_left_right(input_image)
    
    return input_image

def load_image_train(image_file, img_size, num_channels):
    input_image = load(image_file)    
    input_image = random_jitter(input_image, img_size, num_channels)
    input_image = normalize(input_image)
    return input_image

def load_image_test(image_file, img_size):
    input_image = load(image_file)    
    input_image = resize(input_image, img_size, img_size)
    input_image = normalize(input_image)
    return input_image

#%% TRATAMENTO DE EXCEÇÕES
    
class GeneratorError(Exception):
    def __init__(self, gen_model):
        print("O gerador " + gen_model + " é desconhecido")
    
class DiscriminatorError(Exception):
    def __init__(self, disc_model):
        print("O discriminador " + disc_model + " é desconhecido")
        
class LossError(Exception):
    def __init__(self, loss_type):
        print("A loss " + loss_type + " é desconhecida")
        
class LossCompatibilityError(Exception):
    def __init__(self, loss_type, disc_model):
        print("A loss " + loss_type + " não é compatível com o discriminador " + disc_model)

class SizeCompatibilityError(Exception):
    def __init__(self, img_size):
        print("IMG_SIZE " + img_size + " não está disponível")

class TransferUpsampleError(Exception):
    def __init__(self, upsample):
        print("Tipo de upsampling " + upsample + " não definido")