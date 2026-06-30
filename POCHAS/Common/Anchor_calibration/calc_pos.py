import json
import matplotlib.pyplot as plt
from math import *
import numpy as np
from scipy.optimize import least_squares
import json

anchors_dist = {
}

initial_pos = [0.1, 0.0]

def calc_error(xy_est, z_est, dist_real, pos_anchors):
    errores = []

    x = xy_est[0]
    y = xy_est[1]
    z = z_est

    for i in range(len(pos_anchors)):
        dist = dist_real[i]
        pos = pos_anchors[i]

        x_anch = pos[0]
        y_anch = pos[1]
        z_anch = pos[2]

        dist_err = sqrt((abs(x-x_anch))**2+(abs(y-y_anch))**2+(abs(z-z_anch))**2)

        errores.append(dist_err-dist_real[i])


    return errores

def calc_pos(anchors_dist, heights_json):
    
    anchors_pos = {
        '1': [0, 0, 0],
        '2': [0, 0, 0],
        '3': [0, 0, 0],
        '4': [0, 0, 0]
    }

    for idx in anchors_pos:
        anchors_pos[idx][2] = heights_json[idx]
        if idx == '1':
            anchors_pos[idx][0] = 0
            anchors_pos[idx][1] = 0
        elif idx == '2':
            x = sqrt(anchors_dist[(int(idx),1)]**2-(heights_json[idx]-heights_json['1'])**2)
            anchors_pos[idx][0] = x
            anchors_pos[idx][1] = 0
        else:
                '''
                x2 = anchors_pos[str(int(idx)-1)][0]

                r1 = sqrt(anchors_dist[(int(idx),1)]**2-(heights_json[idx]-heights_json[str(int(idx)-1)])**2)
                r2 = sqrt(anchors_dist[(int(idx),int(idx)-1)]**2-(heights_json[str(int(idx)-1)]-heights_json[str(int(idx)-1)])**2)
                x = (r1**2+x2**2-r2**2)/(2*x2)
                y = sqrt(r1**2-x**2)
                
                anchors_pos[idx][0] = x
                anchors_pos[idx][1] = y
                '''
                pos_pre = []
                dist_real = []
                j = 1
                while j<int(idx):
                    d_j = anchors_dist.get((int(idx), j)) or anchors_dist.get((j, int(idx)))
                    pos_j = anchors_pos[str(j)]
                    if d_j is not None:
                        pos_pre.append(pos_j)
                        dist_real.append(d_j)
                    j += 1
                
                result = least_squares(calc_error,initial_pos,args = (heights_json[idx],dist_real, pos_pre))

                anchors_pos[idx][0] = float(result.x[0])
                anchors_pos[idx][1] = float(result.x[1])

    #print(heights_json)
    return anchors_pos

with open('distances.json', 'r') as f:
    with open('heights.json', 'r') as g:
        anchors_json = json.load(f)
        heights_json = json.load(g)
        for idx in anchors_json:
            for idx2 in anchors_json[idx]:
                anchors_from = int(idx)
                anchors_to = int(idx2)
                
                anchors_dist[(anchors_from, anchors_to)] = anchors_json[idx][idx2]
        
        anchors_pos = calc_pos(anchors_dist, heights_json)
        print(anchors_pos)


with open('anchors.json','w',encoding='utf-8') as h:
    json.dump(anchors_pos, h, indent=4, ensure_ascii=False)