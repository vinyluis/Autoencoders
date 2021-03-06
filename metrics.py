import os
import time
import numpy as np

from scipy.linalg import sqrtm
from sklearn.metrics import accuracy_score as accuracy

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'  # Silencia o TF (https://stackoverflow.com/questions/35911252/disable-tensorflow-debugging-information)
import tensorflow as tf
from tensorflow.keras.applications.inception_v3 import InceptionV3

import utils

# %% PREPARAÇÃO

# Prepara o modelo Inception v3 para o IS
model_IS = InceptionV3()

# Prepara o modelo Inception v3 para o FID
model_FID = InceptionV3(include_top=False, pooling='avg', input_shape=(299, 299, 3))

# %% FUNÇÕES BASE


def evaluate_metrics(sample_ds, generator, evaluate_is, evaluate_fid, evaluate_l1, verbose=False):
    """Calcula as métricas de qualidade.

    Calcula Inception Score e Frechét Inception Distance para o gerador.
    Calcula a distância L1 (distância média absoluta pixel a pixel) entre a imagem sintética e a objetivo.
    """
    # Prepara a progression bar
    progbar_iterations = len(list(sample_ds))
    progbar = tf.keras.utils.Progbar(progbar_iterations)

    # Prepara as listas que irão guardar as medidas
    t1 = time.perf_counter()
    inception_score = []
    frechet_inception_distance = []
    l1_distance = []
    c = 0
    for image in sample_ds:

        c += 1
        if verbose:
            print(c)
        else:
            progbar.update(c)

        # Para cada imagem, calcula sua versão sintética
        fake = generator(image)

        try:
            # Cálculos da IS
            if evaluate_is:
                is_score = get_inception_score_gpu(fake)
                inception_score.append(is_score)
                if verbose:
                    print(f"IS = {is_score:.2f}")

            # Cálculos da FID
            if evaluate_fid:
                fid_score = get_frechet_inception_distance_gpu(fake, image)
                frechet_inception_distance.append(fid_score)
                if verbose:
                    print(f"FID = {fid_score:.2f}")

            # Cálculos da L1
            if evaluate_l1:
                l1_score = get_l1_distance(fake, image)
                l1_distance.append(l1_score)
                if verbose:
                    print(f"L1 = {l1_score:.2f}")

        except Exception:
            if verbose:
                print(f"Erro na {c}-ésima iteração. Pulando.")

        if verbose:
            print()

    # Calcula os scores consolidados e salva em um dicionário
    results = {}
    if evaluate_is:
        is_avg, is_std = np.mean(inception_score), np.std(inception_score)
        results['is_avg'] = is_avg
        results['is_std'] = is_std
    if evaluate_fid:
        fid_avg, fid_std = np.mean(frechet_inception_distance), np.std(frechet_inception_distance)
        results['fid_avg'] = fid_avg
        results['fid_std'] = fid_std
    if evaluate_l1:
        l1_avg, l1_std = np.mean(l1_distance), np.std(l1_distance)
        results['l1_avg'] = l1_avg
        results['l1_std'] = l1_std

    # Reporta o resultado
    if verbose:
        if evaluate_is:
            print(f"Inception Score:\nMédia: {is_avg:.2f}\nDesv Pad: {is_std:.2f}\n")
        if evaluate_fid:
            print(f"Fréchet Inception Distance:\nMédia: {fid_avg:.2f}\nDesv Pad: {fid_std:.2f}\n")
        if evaluate_l1:
            print(f"L1 Distance:\nMédia: {l1_avg:.2f}\nDesv Pad: {l1_std:.2f}\n")

    dt = time.perf_counter() - t1
    results['eval_time'] = dt

    return results


def tf_covariance(tensor, rowvar=True):
    return np.cov(tensor, rowvar=rowvar)


def tf_sqrtm(tensor):
    return sqrtm(tensor)


# %% FUNÇÕES DE CÁLCULO DAS MÉTRICAS

# Inception Score
def get_inception_score(image):
    '''
    Calcula o Inception Score (IS) para um único batch de imagens.
    Baseado em: https://machinelearningmastery.com/how-to-implement-the-inception-score-from-scratch-for-evaluating-generated-images/
    '''
    # Epsilon para evitar problemas no cálculo da divergência KL
    eps = 1E-16
    # Redimensiona a imagem
    image = utils.resize(image, 299, 299)
    # Usa o Inception v3 para calcular a probabilidade condicional p(y|x)
    p_yx = model_IS.predict(image)
    # Calcula p(y)
    p_y = np.expand_dims(p_yx.mean(axis=0), 0)
    # Calcula a divergência KL usando probabilididades log
    kl_d = p_yx * (np.log(p_yx + eps) - np.log(p_y + eps))
    # Soma todas as classes da inception
    sum_kl_d = kl_d.sum(axis=1)
    # Faz a média para a imagem
    avg_kl_d = np.mean(sum_kl_d)
    # Desfaz o log
    is_score = np.exp(avg_kl_d)

    return is_score


# Inception Score - GPU
@tf.function
def get_inception_score_gpu(image):
    '''
    Calcula o Inception Score (IS) para uma única imagem.
    Baseado em: https://machinelearningmastery.com/how-to-implement-the-inception-score-from-scratch-for-evaluating-generated-images/
    '''
    # Epsilon para evitar problemas no cálculo da divergência KL
    eps = 1E-16
    # Redimensiona a imagem
    image = utils.resize(image, 299, 299)
    # Usa o Inception v3 para calcular a probabilidade condicional p(y|x)
    p_yx = model_IS(image)
    # Calcula p(y)
    p_y = tf.expand_dims(tf.reduce_mean(p_yx, axis=0), 0)
    # Calcula a divergência KL usando probabilididades log
    kl_d = p_yx * (tf.math.log(p_yx + eps) - tf.math.log(p_y + eps))
    # Soma todas as classes da inception
    sum_kl_d = tf.reduce_sum(kl_d, axis=1)
    # Faz a média para a imagem
    avg_kl_d = tf.reduce_mean(sum_kl_d)
    # Desfaz o log
    is_score = tf.math.exp(avg_kl_d)

    return is_score


# Frechet Inception Distance
def get_frechet_inception_distance(image1, image2):
    '''
    Calcula o Fréchet Inception Distance (FID) entre duas imagens.
    Baseado em: https://machinelearningmastery.com/how-to-implement-the-frechet-inception-distance-fid-from-scratch/
    '''
    # Redimensiona as imagens
    image1 = utils.resize(image1, 299, 299)
    image2 = utils.resize(image2, 299, 299)
    # Calcula as ativações
    act1 = model_FID.predict(image1)
    act2 = model_FID.predict(image2)
    # Calcula as estatísticas de média (mu) e covariância (sigma)
    mu1, sigma1 = act1.mean(axis=0), np.cov(act1, rowvar=False)
    mu2, sigma2 = act2.mean(axis=0), np.cov(act2, rowvar=False)
    # Calcula a distância L2 das médias
    ssdiff = np.sum((mu1 - mu2)**2.0)
    # Calcula a raiz do produto entre as matrizes de covariância
    sigma_dot = sigma1.dot(sigma2)
    covmean = sqrtm(sigma_dot)
    # Corrige números imaginários, se necessário
    if np.iscomplexobj(covmean):
        covmean = covmean.real
    # Calcula o score
    fid = ssdiff + np.trace(sigma1 + sigma2 - 2.0 * covmean)

    return fid


# Frechet Inception Distance - GPU
@tf.function
def get_frechet_inception_distance_gpu(image1, image2):
    '''
    Calcula o Fréchet Inception Distance (FID) entre duas imagens.
    Baseado em: https://machinelearningmastery.com/how-to-implement-the-frechet-inception-distance-fid-from-scratch/
    '''
    # Redimensiona as imagens
    image1 = utils.resize(image1, 299, 299)
    image2 = utils.resize(image2, 299, 299)
    # Calcula as ativações
    act1 = model_FID(image1)
    act2 = model_FID(image2)
    # Calcula as estatísticas de média (mu) e covariância (sigma)
    mu1 = tf.reduce_mean(act1, axis=0)
    mu2 = tf.reduce_mean(act2, axis=0)
    sigma1 = tf.py_function(tf_covariance, inp=[act1, False], Tout=tf.float32)
    sigma2 = tf.py_function(tf_covariance, inp=[act2, False], Tout=tf.float32)
    # Calcula a distância L2 das médias
    ssdiff = tf.reduce_sum((mu1 - mu2)**2.0)
    # Calcula a raiz do produto entre as matrizes de covariância
    # -- Método 1 = Muito lento!!
    # sigma_dot = tf.cast(tf.linalg.matmul(sigma1, sigma2), tf.complex64) # Precisa ser número complexo, senão dá problema
    # covmean = tf.linalg.sqrtm(sigma_dot) # MUITO LENTO!! - Precisa receber um número complexo como entrada, senão dá NAN
    # -- Método 2
    sigma_dot = tf.linalg.matmul(sigma1, sigma2)
    covmean = tf.py_function(tf_sqrtm, inp=[sigma_dot], Tout=tf.complex64)
    # Corrige números imaginários, se necessário
    covmean = tf.math.real(covmean)
    # Calcula o score
    fid = ssdiff + tf.linalg.trace(sigma1 + sigma2 - 2.0 * covmean)

    return fid


# L1 Distance
@tf.function
def get_l1_distance(image1, image2):
    '''Calcula a distância L1 (distância média absoluta pixel a pixel) entre duas imagens'''
    l1_dist = tf.reduce_mean(tf.abs(image1 - image2))
    return l1_dist


# Acurácia do discriminador
def evaluate_accuracy(generator, discriminator, test_ds, y_real, y_pred, window=100):
    """Avalia a acurácia do discriminador, como um classificador binário."""
    # Gera uma imagem-base
    for img_real in test_ds.take(1):
        target = img_real

        # A partir dela, gera uma imagem sintética
        img_fake = generator(img_real, training=True)

        # Avalia ambas
        disc_real = discriminator([img_real, target], training=True)
        disc_fake = discriminator([img_fake, target], training=True)

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


# %% TESTE

if __name__ == "__main__":

    root_path = '../../0_Datasets/celeba_hq/train/male/'

    # LOAD IMAGES
    filepath1 = root_path + '000016.jpg'
    image1_raw = utils.load_image_test(filepath1, 256)  # Load image
    image1_raw = np.random.uniform(low=-1, high=1, size=image1_raw.shape) + image1_raw  # Add noise
    image1 = np.expand_dims(image1_raw, axis=0)  # Add a dimension for batch

    filepath2 = root_path + '000025.jpg'
    image2_raw = utils.load_image_test(filepath2, 256)  # Load image
    image2_raw = np.random.uniform(low=-1, high=1, size=image2_raw.shape) + image2_raw  # Add noise
    image2 = np.expand_dims(image2_raw, axis=0)  # Add a dimension for batch

    filepath3 = root_path + '000030.jpg'
    image3_raw = utils.load_image_test(filepath3, 256)  # Load image
    image3_raw = np.random.uniform(low=-1, high=1, size=image3_raw.shape) + image3_raw  # Add noise
    image3 = np.expand_dims(image3_raw, axis=0)  # Add a dimension for batch

    filepath4 = root_path + '000051.jpg'
    image4_raw = utils.load_image_test(filepath4, 256)  # Load image
    image4_raw = np.random.uniform(low=-1, high=1, size=image4_raw.shape) + image4_raw  # Add noise
    image4 = np.expand_dims(image4_raw, axis=0)  # Add a dimension for batch

    concat1 = tf.concat([image1, image2], 0)
    concat2 = tf.concat([image3, image4], 0)
    concat_all = tf.concat([image1, image2, image3, image4], 0)

    # PRINT IMAGES (IF SO)
    '''
    import matplotlib.pyplot as plt
    plt.imshow(image1_raw * 0.5 + 0.5) # getting the pixel values between [0, 1] to plot it.
    plt.show()
    plt.figure()
    plt.imshow(image2_raw * 0.5 + 0.5) # getting the pixel values between [0, 1] to plot it.
    plt.show()
    plt.figure()
    plt.imshow(image3_raw * 0.5 + 0.5) # getting the pixel values between [0, 1] to plot it.
    plt.show()
    plt.figure()
    plt.imshow(image4_raw * 0.5 + 0.5) # getting the pixel values between [0, 1] to plot it.
    plt.show()
    '''

    # INCEPTION SCORE
    print("\nCalculando IS")
    t = time.perf_counter()
    is_score = get_inception_score(concat_all)
    print(f"IS = {is_score:.4f}")
    dt = time.perf_counter() - t
    print(f"A avaliação do IS com Numpy levou {dt:.2f} s")

    # INCEPTION SCORE - GPU
    print("\nCalculando IS - GPU")
    t = time.perf_counter()
    is_score = get_inception_score_gpu(concat_all)
    print(f"IS = {is_score:.4f}")
    dt = time.perf_counter() - t
    print(f"A avaliação do IS com TF levou {dt:.2f} s")

    # INCEPTION SCORE - GPU
    print("\nCalculando IS - GPU (repetição)")
    t = time.perf_counter()
    is_score = get_inception_score_gpu(concat_all)
    print(f"IS = {is_score:.4f}")
    dt = time.perf_counter() - t
    print(f"A avaliação do IS com TF levou {dt:.2f} s")

    # FRECHET INCEPTION DISTANCE
    print("\nCalculando FID")
    t = time.perf_counter()
    fid_score = get_frechet_inception_distance(concat1, concat2)
    print(f"FID = {fid_score:.4f}")
    dt = time.perf_counter() - t
    print(f"A avaliação do FID com Numpy levou {dt:.2f} s")

    # FRECHET INCEPTION DISTANCE - GPU
    print("\nCalculando FID - GPU")
    t = time.perf_counter()
    fid_score = get_frechet_inception_distance_gpu(concat1, concat2)
    print(f"FID = {fid_score:.4f}")
    dt = time.perf_counter() - t
    print(f"A avaliação do FID com TF levou {dt:.2f} s")

    # FRECHET INCEPTION DISTANCE - GPU
    print("\nCalculando FID - GPU (repetição)")
    t = time.perf_counter()
    fid_score = get_frechet_inception_distance_gpu(concat1, concat2)
    print(f"FID = {fid_score:.4f}")
    dt = time.perf_counter() - t
    print(f"A avaliação do FID com TF levou {dt:.2f} s")

    # L1
    print("\nCalculando L1")
    t = time.perf_counter()
    l1 = get_l1_distance(concat1, concat2)
    print(f"L1 = {l1:.4f}")
    dt = time.perf_counter() - t
    print(f"A avaliação do L1 com TF levou {dt:.2f} s")

    # L1
    print("\nCalculando L1 - Repetição")
    t = time.perf_counter()
    l1 = get_l1_distance(concat1, concat2)
    print(f"L1 = {l1:.4f}")
    dt = time.perf_counter() - t
    print(f"A avaliação do L1 com TF levou {dt:.2f} s")
