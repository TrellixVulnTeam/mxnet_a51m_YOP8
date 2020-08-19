/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

/*!
 * \file PermuteGenerator.java
 * \brief Generate Permute layer
 */

package io.mxnet.caffetranslator.generators;

import io.mxnet.caffetranslator.GeneratorOutput;
import io.mxnet.caffetranslator.Layer;
import io.mxnet.caffetranslator.MLModel;
import org.stringtemplate.v4.ST;

import java.util.List;

public class PermuteGenerator extends BaseGenerator {

    @Override
    public GeneratorOutput generate(Layer layer, MLModel model) {
        ST st = getTemplate("permute");
        gh.fillNameDataAndVar(st, layer);

        List<String> axes = layer.getAttrList("permute_param.order");
        if (axes != null) {
            st.add("axes", axes);
        }

        return new GeneratorOutput(st.render(), 1);
    }
}
