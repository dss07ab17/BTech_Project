'''
This is a part of the supplementary material uploaded along with 
the manuscript:

    "Lung Pattern Classification for Interstitial Lung Diseases Using a Deep Convolutional Neural Network"
    M. Anthimopoulos, S. Christodoulidis, L. Ebner, A. Christe and S. Mougiakakou
    IEEE Transactions on Medical Imaging (2016)
    http://dx.doi.org/10.1109/TMI.2016.2535865

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

For more information please read the README file. The files can also 
be found at: https://github.com/intact-project/ild-cnn
'''
import re
import os
import sys
import cv2
import pickle
import numpy as np
import ild_helpers as H
#import h5py
from tensorflow import keras
import keras
from keras.models import Sequential
from tensorflow.keras.layers import Dense, Dropout, Flatten, Activation
from tensorflow.keras.layers import Convolution2D, MaxPooling2D,AveragePooling2D
from tensorflow.keras.layers import LeakyReLU
from keras.models import load_model

print (keras.__version__)
# debug
# from ipdb import set_trace as bp
from tensorflow.keras.initializers import Orthogonal,HeUniform
def get_FeatureMaps(L, policy, constant=17):
    return {
        'proportional': (L+1)**2,
        'static': constant,
    }[policy]

def get_Obj(obj):
    return {
        'mse': 'MSE',
        'ce': 'categorical_crossentropy',
    }[obj]

def get_model(input_shape, output_shape, params):

    print('compiling model...')
        
    # Dimension of The last Convolutional Feature Map (eg. if input 32x32 and there are 5 conv layers 2x2 fm_size = 27)
    fm_size = input_shape[-1] - params['cl']
    print ('fm_size : ', fm_size)
    print ('input_shape[-1] : ', input_shape[-1])
    print ('number of convolutional layers : ', params['cl'])
    
    # Tuple with the pooling size for the last convolutional layer using the params['pf']
    pool_siz = (np.round(fm_size*params['pf']).astype(int), np.round(fm_size*params['pf']).astype(int))
    
    # Initialization of the model
    model = Sequential()
    params['fp'] = 'static'  # or 'proportional' based on your model's requirement
    # Add convolutional layers to model
    # model.add(Convolution2D(params['k']*get_FeatureMaps(1, params['fp']), 2, 2, init='orthogonal', activation=LeakyReLU(params['a']), input_shape=input_shape[1:]))
    # added by me
    model.add(Convolution2D(params['k']*get_FeatureMaps(1, params['fp']), 2, 2, kernel_initializer=Orthogonal(),padding="SAME", input_shape=input_shape[1:]))
    # model.add(Activation('relu'))
    model.add(LeakyReLU(alpha=params['a']))
    print ('Layer 1 parameters settings:')
    print ('number of filters to be used : ', params['k']*get_FeatureMaps(1, params['fp']))
    print ('kernel size : 2 x 2' )
    print ('input_shape of tensor is : ', input_shape[1:])

    for i in range(2, params['cl']+1):
        # model.add(Convolution2D(params['k']*get_FeatureMaps(i, params['fp']), 2, 2, init='orthogonal', activation=LeakyReLU(params['a'])))
        model.add(Convolution2D(params['k']*get_FeatureMaps(i, params['fp']), 2, 2, kernel_initializer=Orthogonal()))
        # model.add(Activation('relu'))
        model.add(LeakyReLU(alpha=params['a']))
        print ('Layer',  i, ' parameters settings:')
        print ('number of filters to be used : ', params['k']*get_FeatureMaps(i, params['fp']))
        print ('kernel size : 2 x 2' )


    # Add Pooling and Flatten layers to model
    print ('entering 2D Pooling layer')
    print ('Pooling : ', params['pt'])
    print ('pool_size : ', pool_siz)
    feature_maps = get_FeatureMaps(params['cl'], params['fp'])

    print(f"DEBUG: Input to pooling layer has shape {model.output_shape}")
    input_shape = model.output_shape[1:3]  # Extract (height, width)
    pool_siz = min(input_shape[0], input_shape[1], max(1, int(get_FeatureMaps(params['cl'], params['fp']) / params['pf'])))

   
    if pool_siz > input_shape[0] or pool_siz > input_shape[1]:
        print(f"WARNING: Pool size {pool_siz} is larger than input shape {input_shape}. Adjusting...")
        pool_siz = min(input_shape[0], input_shape[1])  # Adjust to valid size

    print(f"Using pool size: {pool_siz}")
    model.add(AveragePooling2D(pool_size=(pool_siz, pool_siz)))



    model.add(Flatten())

    # dropout is 50% or do=0.5
    model.add(Dropout(params['do']))

    # Add Dense layers and Output to model
    # model.add(Dense(int(params['k']*get_FeatureMaps(params['cl'], params['fp']))/params['pf']*6, init='he_uniform', activation=LeakyReLU(0)))
    model.add(Dense(int(params['k']*get_FeatureMaps(params['cl'], params['fp'])/params['pf']*6), kernel_initializer=HeUniform()))
    
    print ('output_dimension : ', int(params['k']*get_FeatureMaps(params['cl'], params['fp'])/params['pf']*6))

    # model.add(Activation('relu'))
    model.add(LeakyReLU(alpha=params['a']))
    model.add(Dropout(params['do']))

    
    # model.add(Dense(int(params['k']*get_FeatureMaps(params['cl'], params['fp']))/params['pf']*2, init='he_uniform', activation=LeakyReLU(0)))
    model.add(Dense(int(params['k']*get_FeatureMaps(params['cl'], params['fp'])/params['pf']*2), kernel_initializer=HeUniform()))
    #  model.add(Activation('relu'))
    model.add(LeakyReLU(alpha=params['a']))
    model.add(Dropout(params['do']))
    model.add(Dense(output_shape[1], kernel_initializer=HeUniform(), activation='softmax'))



#sk modif for decay, works only with ADAM

    decay = 0.001
    lr=0.001
    
    # Compile model and select optimizer and objective function
    if params['opt'] not in ['Adam', 'Adagrad', 'SGD']:
        sys.exit('Wrong optimizer: Please select one of the following. Adam, Adagrad, SGD')
    if get_Obj(params['obj']) not in ['MSE', 'categorical_crossentropy']:
        sys.exit('Wrong Objective: Please select one of the following. MSE, categorical_crossentropy')
#    model.compile(optimizer=params['opt'], loss=get_Obj(params['obj']))

    optimizer=keras.optimizers.Adam(learning_rate=lr,decay=decay)
    model.compile(optimizer=optimizer, loss=get_Obj(params['obj']))

    return model

def train(x_train, y_train, x_val, y_val, params,class_weights):
    ''' TODO: documentation '''

    
    # Parameters String used for saving the files
    parameters_str = str('_d' + str(params['do']).replace('.', '') +
                         '_a' + str(params['a']).replace('.', '') + 
                         '_k' + str(params['k']).replace('.', '') + 
                         '_c' + str(params['cl']).replace('.', '') + 
                         '_s' + str(params['s']).replace('.', '') + 
                         '_pf' + str(params['pf']).replace('.', '') + 
                         '_pt' + params['pt'] +
                         '_fp' + str(params['fp']).replace('.', '') +
                         '_opt' + params['opt'] +
                         '_obj' + params['obj'])

    # Printing the parameters of the model
    print('[Dropout Param] \t->\t'+str(params['do']))
    print('[Alpha Param] \t\t->\t'+str(params['a']))
    print('[Multiplier] \t\t->\t'+str(params['k']))
    print('[Patience] \t\t->\t'+str(params['patience']))
    print('[Tolerance] \t\t->\t'+str(params['tolerance']))
    print('[Input Scale Factor] \t->\t'+str(params['s']))
    print('[Pooling Type] \t\t->\t'+ params['pt'])
    print('[Pooling Factor] \t->\t'+str(str(params['pf']*100)+'%'))
    print('[Feature Maps Policy] \t->\t'+ params['fp'])
    print('[Optimizer] \t\t->\t'+ params['opt'])
    print('[Objective] \t\t->\t'+ get_Obj(params['obj']))
    print('[Results filename] \t->\t'+str(params['res_alias']+parameters_str+'.txt'))

    # Rescale Input Images
    if params['s'] != 1:
        print('\033[93m'+'Rescaling Patches...'+'\033[0m')
        x_train = np.asarray(np.expand_dims([cv2.resize(x_train[i, 0, :, :], (0,0), fx=params['s'], fy=params['s']) for i in xrange(x_train.shape[0])], 1))
        x_val = np.asarray(np.expand_dims([cv2.resize(x_val[i, 0, :, :], (0,0), fx=params['s'], fy=params['s']) for i in xrange(x_val.shape[0])], 1))
        print('\033[92m'+'Done, Rescaling Patches'+'\033[0m')
        print('[New Data Shape]\t->\tX: '+str(x_train.shape))

    print ('x_shape is: ', x_train.shape)

    if os.path.exists('../pickle/ILD_CNN_model.h5'):
        print('Model exists')  
        model = H.load_model('../pickle/ILD_CNN_model.h5')
    else:
        print ('restart from 0')
        model = get_model(x_train.shape, y_train.shape, params)
    # Counters-buffers
    maxf         = 0
    maxacc       = 0
    maxit        = 0
    maxtrainloss = 0
    maxvaloss    = np.inf
    best_model   = model
    it           = 0    
    p            = 0
    # Open file to write the results
    

    # Remove invalid characters for filenames
    safe_res_alias = re.sub(r'[\\/*?:"<>|]', '_', params['res_alias'])
    safe_parameters_str = re.sub(r'[\\/*?:"<>|]', '_', parameters_str)

    open('../pickle/' + safe_res_alias + safe_parameters_str + '.csv', 'a').write('Epoch, Val_fscore, Val_acc, Train_loss, Val_loss\n')
    open('../pickle/' + safe_res_alias + safe_parameters_str + '-Best.csv', 'a').write('Epoch, Val_fscore, Val_acc, Train_loss, Val_loss\n')


    print ('starting the loop of training with number of patience = ', params['patience'])
    
    while p < params['patience']:
        p += 1

        # Fit the model for one epoch
        print('Epoch: ' + str(it))
        history = model.fit(x_train, y_train, batch_size=250, epochs=1, validation_data=(x_val,y_val), shuffle=True,class_weight=class_weights)

    
        # Evaluate models
        y_score = model.predict(x_val, batch_size=1050)

        fscore, acc, cm = H.evaluate(np.argmax(y_val, axis=1), np.argmax(y_score, axis=1))
        print('Val F-score: '+str(fscore)+'\tVal acc: '+str(acc))

        # Write results in file

        # Fix the filename by removing forbidden characters
        safe_filename = re.sub(r'[<>:"/\\|?*]', '_', params['res_alias'] + parameters_str)  

        # Ensure the directory exists before writing the file
        
        os.makedirs('../pickle/', exist_ok=True)

        # Write results in a properly formatted file
        with open(f'../pickle/{safe_filename}.csv', 'a') as file:
           file.write(f"{it}, {fscore}, {acc}, {np.max(history.history['loss'])}, {np.max(history.history['val_loss'])}\n")


        # check if current state of the model is the best and write evaluation metrics to file
        if fscore > maxf*params['tolerance']:  # if fscore > maxf*params['tolerance']:
            print ('fscore is still bigger than last iterations fscore + 5%')
            #p            = 0  # restore patience counter
            best_model   = model  # store current model state
            maxf         = fscore 
            maxacc       = acc
            maxit        = it
            maxtrainloss = np.max(history.history['loss'])
            maxvaloss    = np.max(history.history['val_loss'])

            print(np.round(100*cm/np.sum(cm,axis=1).astype(float)))

            # ✅ Ensure the output directory exists
            # ✅ Ensure the output directory exists
            safe_filename = re.sub(r'[<>:"/\\|?*]', '_', params['res_alias'] + parameters_str)  

            # Ensure the directory exists before writing the file
        
            os.makedirs('../pickle/', exist_ok=True)

            # Write results in a properly formatted file
            with open(f'../pickle/{safe_filename}.csv', 'a') as file:
                file.write(f"{it}, {fscore}, {acc}, {np.max(history.history['loss'])}, {np.max(history.history['val_loss'])}\n")
            H.store_model(best_model)
        it += 1
    
    print('Max: fscore:', maxf, 'acc:', maxacc, 'epoch: ', maxit, 'train loss: ', maxtrainloss, 'validation loss: ', maxvaloss)

    return best_model


def prediction(X_test, y_test, params):
    f=open ('../pickle/res.txt','w')
    model = H.load_model()
    #model= H.load_model('../pickle/ILD_CNN_model.h5')
    model.compile(optimizer='Adam', loss=get_Obj(params['obj']))

    y_classes = model.predict(X_test, batch_size=100)
    y_val_subset = y_classes[:]
    y_test_subset = y_test[:]  # Check its shape

    # Fix: Only apply argmax if y_test is one-hot encoded
    if len(y_test_subset.shape) > 1:  
        y_predict = np.argmax(y_test_subset, axis=1)  
    else:  
        y_predict = y_test_subset  # Already class labels

    y_actual = np.argmax(y_val_subset, axis=1)  # Convert model output to class labels

    fscore, acc, cm = H.evaluate(y_actual, y_predict)



    print ('f-score is : ', fscore)
    print ('accuracy is : ', acc)
    print ('confusion matrix')
    print (cm)
    f.write('f-score is : '+ str(fscore)+'\n')
    f.write( 'accuracy is : '+ str(acc)+'\n')
    f.write('confusion matrix\n')
    n= cm.shape[0]
    for i in range (0,n):
        for j in range (0,n):
           f.write(str(cm[i][j])+' ')
        f.write('\n')
    f.close()
    open('../' + 'TestLog.csv', 'a').write(str(params['res_alias']) + ', ' + str(str(fscore) + ', ' + str(acc)+'\n'))
    return