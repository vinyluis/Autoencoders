# FUNÇÕES DE APOIO PARA O AUTOENCODER

import os
import matplotlib.pyplot as plt
import wandb
from datetime import datetime
from datetime import timedelta

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Silencia o TF (https://stackoverflow.com/questions/35911252/disable-tensorflow-debugging-information)
import tensorflow as tf

from sklearn.metrics import accuracy_score as accuracy

#%% FUNÇÕES DE APOIO

def dict_tensor_to_numpy(tensor_dict):
    numpy_dict = {}
    for k in tensor_dict.keys():
        try:
            numpy_dict[k] = tensor_dict[k].numpy()
        except:
            numpy_dict[k] = tensor_dict[k]
    return numpy_dict

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
    
def generate_images(generator, img_input, save_destination = None, filename = None, QUIET_PLOT = True):
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
    
    if save_destination != None and filename != None:
        f.savefig(save_destination + filename)

    if not QUIET_PLOT:
        f.show()
        return f
    else:
        plt.close(f)

def generate_fixed_images(fixed_train, fixed_val, generator, epoch, EPOCHS, save_folder, QUIET_PLOT = True, log_wandb = True):

    # Train
    filename_train = "train_epoch_" + str(epoch).zfill(len(str(EPOCHS))) + ".jpg"
    fig_train = generate_images(generator, fixed_train, save_folder, filename_train, QUIET_PLOT = False)

    # Val
    filename_val = "val_epoch_" + str(epoch).zfill(len(str(EPOCHS))) + ".jpg"
    fig_val = generate_images(generator, fixed_val, save_folder, filename_val, QUIET_PLOT = False)

    if log_wandb:
        wandb_title = "Época {}".format(epoch)

        wandb_fig_train = wandb.Image(fig_train, caption="Train")
        wandb_title_train =  wandb_title + " - Train"

        wandb_fig_val = wandb.Image(fig_val, caption="Val")
        wandb_title_val =  wandb_title + " - Val"

        wandb.log({wandb_title_train: wandb_fig_train,
                wandb_title_val: wandb_fig_val})

    if QUIET_PLOT:
        plt.close(fig_train)
        plt.close(fig_val)


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